def get_cortex_complete_cost(model_name: str, input_tokens: int, output_tokens: int, credit_price_usd: float = 2.73) -> dict:
    """
    Calculate the cost of a Cortex AI_COMPLETE call.
    
    Args:
        model_name: The LLM model name (e.g., 'llama3.1-70b', 'claude-3-5-sonnet')
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        credit_price_usd: Price per Snowflake credit in USD (default $2.73)
    
    Returns:
        dict with credits used and USD cost
    """
    
    CREDIT_RATES = {
        # Large Models
        'claude-4-sonnet': {'input': 1.80, 'output': 9.00},
        'claude-3-7-sonnet': {'input': 1.80, 'output': 9.00},
        'claude-3-5-sonnet': {'input': 0.90, 'output': 2.70},
        'claude-sonnet-4-5': {'input': 1.80, 'output': 9.00},
        'claude-opus-4-5': {'input': 9.00, 'output': 27.00},
        'claude-haiku-4-5': {'input': 0.60, 'output': 3.00},
        'deepseek-r1': {'input': 0.33, 'output': 1.32},
        'gemini-3-pro': {'input': 0.75, 'output': 3.00},
        'llama4-maverick': {'input': 0.18, 'output': 0.54},
        'llama4-scout': {'input': 0.10, 'output': 0.34},
        'llama3.1-405b': {'input': 1.32, 'output': 3.96},
        'snowflake-llama-3.1-405b': {'input': 0.33, 'output': 0.99},
        'openai-gpt-4.1': {'input': 1.20, 'output': 4.80},
        'openai-gpt-5': {'input': 9.00, 'output': 27.00},
        'openai-gpt-5-mini': {'input': 0.69, 'output': 2.76},
        'openai-gpt-5-nano': {'input': 0.06, 'output': 0.24},
        'openai-gpt-5-chat': {'input': 1.50, 'output': 6.00},
        
        # Medium Models
        'llama3.1-70b': {'input': 0.29, 'output': 0.87},
        'llama3.3-70b': {'input': 0.29, 'output': 0.87},
        'snowflake-llama-3.3-70b': {'input': 0.10, 'output': 0.30},
        'mistral-large2': {'input': 0.57, 'output': 1.71},
        'mixtral-8x7b': {'input': 0.06, 'output': 0.18},
        'snowflake-arctic': {'input': 0.24, 'output': 0.84},
        
        # Small Models
        'llama3.1-8b': {'input': 0.03, 'output': 0.09},
        'mistral-7b': {'input': 0.03, 'output': 0.09},
        
        # Legacy Models
        'llama3-70b': {'input': 0.29, 'output': 0.87},
        'llama3-8b': {'input': 0.03, 'output': 0.09},
        'mistral-large': {'input': 0.57, 'output': 1.71},
    }
    
    model_key = model_name.lower()
    
    if model_key not in CREDIT_RATES:
        raise ValueError(f"Unknown model: {model_name}. Available models: {list(CREDIT_RATES.keys())}")
    
    rates = CREDIT_RATES[model_key]
    
    input_credits = (input_tokens / 1_000_000) * rates['input']
    output_credits = (output_tokens / 1_000_000) * rates['output']
    total_credits = input_credits + output_credits
    
    return {
        'model': model_name,
        'input_tokens': input_tokens,
        'output_tokens': output_tokens,
        'input_credits': round(input_credits, 6),
        'output_credits': round(output_credits, 6),
        'total_credits': round(total_credits, 6),
        'cost_usd': round(total_credits * credit_price_usd, 4),
        'credit_price_usd': credit_price_usd
    }