import os
import argparse

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    from transformers import cache_utils
    
    # Monkey patch DynamicCache for compatibility with models using seen_tokens (like DeepSeek)
    if hasattr(cache_utils, "DynamicCache"):
        if not hasattr(cache_utils.DynamicCache, "seen_tokens"):
            @property
            def seen_tokens(self):
                return self.get_seq_length()
            cache_utils.DynamicCache.seen_tokens = seen_tokens
        
        if not hasattr(cache_utils.DynamicCache, "get_max_length"):
            def get_max_length(self):
                return self.get_seq_length() - 1
            cache_utils.DynamicCache.get_max_length = get_max_length

    LOCAL_MODELS_AVAILABLE = True
except ImportError:
    LOCAL_MODELS_AVAILABLE = False
    print("Warning: 'transformers' or 'torch' not found. Local models will not be available.")

from openai import OpenAI
from anthropic import Anthropic
from google import genai

try:
    from api_resouce import openai_api, gemini_api, claude_api
except ImportError:
    print("Warning: api_resouce.py not found or keys missing.")
    openai_api = os.environ.get("OPENAI_API_KEY")
    gemini_api = os.environ.get("GOOGLE_API_KEY")
    claude_api = os.environ.get("ANTHROPIC_API_KEY")

# 初始化客户端 (优先使用 api_resouce.py 中的 key，如果没有则尝试环境变量)
# 注意：DeepSeek 等开源模型通常兼容 OpenAI SDK，可能需要单独的 Key，这里假设复用 openai_api 或需要用户在 api_resouce 中补充
# 为了方便，这里暂时假设 deepseek 使用 openai_api 或者环境变量 DEEPSEEK_API_KEY
deepseek_api = os.environ.get("DEEPSEEK_API_KEY")

def prompt_llm(model: str, prompt: str, system_prompt: str = None) -> str:
    """
    通用 LLM 调用接口
    
    Args:
        model: 模型名称，支持：
            - OpenAI: "gpt-4o", "gpt-4o-mini"
            - Google: "gemini-2.0-flash", "gemini-2.0-pro-exp-02-05" (mapped from "gemini-2.0")
            - Anthropic: "claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"
            - Local (Hugging Face):
              "llama-3.1-8b-instruct" -> "meta-llama/Llama-3.1-8B-Instruct"
              "qwen2.5-coder-7b-instruct" -> "Qwen/Qwen2.5-Coder-7B-Instruct"
              "qwen2.5-32b-instruct" -> "Qwen/Qwen2.5-32B-Instruct" (注意这里修改了映射 key)
              "deepseek-coder-v2-lite-instruct" -> "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct"
        prompt: 用户输入的 prompt
        system_prompt: 可选的系统提示词
        
    Returns:
        生成的文本内容
    """
    
    # 统一模型名称映射 (处理用户输入的别名)
    model_map = {
        # OpenAI
        "gpt-4o": "gpt-4o",
        "gpt-4o-mini": "gpt-4o-mini",
        
        # Google
        "gemini-2.0": "gemini-2.0-pro-exp-02-05", # 假设 gemini-2.0 映射到当前的预览版或可用版本
        "gemini-2.0-flash": "gemini-2.0-flash",
        
        # Anthropic
        "claude-3.5-haiku": "claude-3-5-haiku-latest",
        "claude-3.5-sonnet": "claude-3-5-sonnet-latest",
        
        # Local / Hugging Face Models
        "llama-3.1-8b-instruct": "meta-llama/Llama-3.1-8B-Instruct", 
        "qwen2.5-coder-7b-instruct": "Qwen/Qwen2.5-Coder-7B-Instruct",
        "qwen2.5-coder-32b": "Qwen/Qwen2.5-32B-Instruct", # 用户之前用的 key 是这个
        "qwen2.5-32b-instruct": "Qwen/Qwen2.5-32B-Instruct", # 增加一个别名
        "deepseek-coder-v2-lite-instruct": "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
    }
    
    # 标准化输入 key
    normalized_model = model.lower()
    # 尝试找到映射后的模型名
    target_model = model_map.get(normalized_model, model) 

    try:
        # 判断是否为本地/HF模型
        is_local_model = any(x in target_model for x in ["meta-llama", "Qwen", "deepseek-ai"])
        
        if is_local_model:
            if not LOCAL_MODELS_AVAILABLE:
                return f"Error: Local models are not supported in this environment (transformers/torch missing)."

            print(f"Loading local model: {target_model}...")
            # 4-bit 量化配置
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16
            )
            
            # 加载模型
            tokenizer = AutoTokenizer.from_pretrained(target_model, trust_remote_code=True)
            
            # DeepSeek specific: disable flash attention if not installed
            attn_implementation = None
            if "deepseek" in target_model.lower():
                attn_implementation = "eager"

            model_kwargs = {
                "quantization_config": bnb_config,
                "device_map": "auto",
                "trust_remote_code": True,
            }
            if attn_implementation:
                model_kwargs["attn_implementation"] = attn_implementation

            model_instance = AutoModelForCausalLM.from_pretrained(
                target_model,
                **model_kwargs
            )
            
            # 构造输入
            full_prompt = prompt
            if system_prompt:
                # 简单的系统提示词拼接，不同模型可能有不同的 chat template，这里做通用处理
                # 如果模型支持 apply_chat_template 最好用那个，这里为了通用性简单拼接
                # 更好的方式是使用 tokenizer.apply_chat_template
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
                try:
                    text = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True
                    )
                    full_prompt = text
                except Exception:
                    # 如果模板不支持 system role 或者出错，回退到简单拼接
                    full_prompt = f"{system_prompt}\n\n{prompt}"
            else:
                 messages = [{"role": "user", "content": prompt}]
                 try:
                    text = tokenizer.apply_chat_template(
                        messages,
                        tokenize=False,
                        add_generation_prompt=True
                    )
                    full_prompt = text
                 except Exception:
                    pass

            inputs = tokenizer(full_prompt, return_tensors="pt").to("cuda")
            
            # 生成
            outputs = model_instance.generate(
                **inputs,
                max_new_tokens=1024,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
            
            # 解码 (只返回生成的响应部分)
            # 简单的做法是直接 decode 整个 output，然后去掉 input 部分
            generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # 尝试去除 input prompt 部分，只保留回答
            # 注意：由于 tokenizer.decode 可能会去除特殊 token，导致字符串匹配不完全准确
            # 这里简单尝试，如果不行就返回全部
            # 对于 chat 模板，通常 input 和 output 有明显界限
            # 更严谨的做法是 inputs['input_ids'].shape[1] 之后的内容
            input_length = inputs['input_ids'].shape[1]
            generated_response = tokenizer.decode(outputs[0][input_length:], skip_special_tokens=True)
            
            return generated_response

        elif "gpt" in target_model:
            client = OpenAI(api_key=openai_api)
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model=target_model,
                messages=messages
            )
            return response.choices[0].message.content

        elif "gemini" in target_model:
            # 使用新的 google-genai SDK
            client = genai.Client(api_key=gemini_api)
            
            kwargs = {}
            if system_prompt:
                 kwargs['config'] = {'system_instruction': system_prompt}

            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                **kwargs
            )
            return response.text

        elif "claude" in target_model:
            client = Anthropic(api_key=claude_api)
            messages = [{"role": "user", "content": prompt}]
            
            # Anthropic system prompt 是单独的参数
            kwargs = {
                "model": target_model,
                "max_tokens": 1024,
                "messages": messages
            }
            if system_prompt:
                kwargs["system"] = system_prompt
                
            response = client.messages.create(**kwargs)
            return response.content[0].text

        else:
            # Fallback for other models or if logic above missed
             return f"Error: Model {model} not supported or recognized."

    except Exception as e:
        return f"Error invoking {model}: {str(e)}"

if __name__ == "__main__":
    # 测试代码
    test_models = [
        # "gpt-4o", 
        # "gpt-4o-mini", 
        # "gemini-2.0", 
        # "gemini-2.0-flash", 
        # "claude-3.5-haiku", 
        # "claude-3.5-sonnet", 
        "llama-3.1-8b-instruct", 
        "qwen2.5-coder-7b-instruct", 
        "qwen2.5-coder-32b", 
        "deepseek-coder-v2-lite-instruct"
    ]

    prompt = "请用 Python 写一个斐波那契数列生成函数，返回前10个数。"
    system_prompt = "你是一个乐于助人的编程助手。"

    print(f"Testing Prompt: {prompt}\n")

    for model in test_models:
        print(f"--- Testing Model: {model} ---")
        result = prompt_llm(model, prompt, system_prompt)
        print(f"Result:\n{result}\n")
        print("-" * 50 + "\n")
