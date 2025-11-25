"""Model loading utilities with quantization support."""

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from typing import Tuple, Optional, Literal
import warnings

# Try to import quantization libraries
try:
    from transformers import BitsAndBytesConfig
    HAS_BITSANDBYTES = True
except ImportError:
    HAS_BITSANDBYTES = False
    warnings.warn(
        "bitsandbytes not available. Quantization (4bit, 8bit) will not work. "
        "This is expected on macOS. Use 'bf16' or 'fp16' instead."
    )

QuantizationType = Literal["bf16", "fp16", "8bit", "4bit"]


def load_model(
    model_name: str,
    quantization: QuantizationType = "bf16",
    device_map: str = "auto",
    trust_remote_code: bool = True,
) -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
    """
    Load model with specified quantization.

    Args:
        model_name: HuggingFace model identifier
        quantization: Quantization type - bf16, fp16, 8bit, or 4bit
        device_map: Device mapping strategy
        trust_remote_code: Whether to trust remote code

    Returns:
        Tuple of (model, tokenizer)
    """
    print(f"Loading model: {model_name}")
    print(f"Quantization: {quantization}")

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=trust_remote_code
    )

    # Set pad token if not present
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Configure quantization
    if quantization == "4bit":
        if not HAS_BITSANDBYTES:
            warnings.warn(
                "4-bit quantization requested but bitsandbytes not available. "
                "Falling back to bf16. Install with: pip install bitsandbytes"
            )
            quantization = "bf16"
        else:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4"
            )
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=bnb_config,
                device_map=device_map,
                trust_remote_code=trust_remote_code,
            )
            print(f"Model loaded with 4-bit quantization")
            return model, tokenizer

    if quantization == "8bit":
        if not HAS_BITSANDBYTES:
            warnings.warn(
                "8-bit quantization requested but bitsandbytes not available. "
                "Falling back to bf16."
            )
            quantization = "bf16"
        else:
            model = AutoModelForCausalLM.from_pretrained(
                model_name,
                load_in_8bit=True,
                device_map=device_map,
                trust_remote_code=trust_remote_code,
            )
            print(f"Model loaded with 8-bit quantization")
            return model, tokenizer

    if quantization == "fp16":
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map=device_map,
            trust_remote_code=trust_remote_code,
        )
        print(f"Model loaded with FP16 precision")

    else:  # bf16 (default fallback)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map=device_map,
            trust_remote_code=trust_remote_code,
        )
        print(f"Model loaded with BF16 precision")

    # Print model info
    try:
        param_count = sum(p.numel() for p in model.parameters())
        print(f"Total parameters: {param_count:,}")
        trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
        print(f"Trainable parameters: {trainable_params:,}")
    except Exception as e:
        print(f"Could not compute parameter count: {e}")

    return model, tokenizer


def generate_text(
    model: AutoModelForCausalLM,
    tokenizer: AutoTokenizer,
    prompt: str,
    max_new_tokens: int = 256,
    temperature: float = 0.1,
    top_p: float = 0.95,
    do_sample: bool = True,
) -> str:
    """
    Generate text using the model.

    Args:
        model: Loaded model
        tokenizer: Loaded tokenizer
        prompt: Input prompt
        max_new_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        top_p: Nucleus sampling parameter
        do_sample: Whether to use sampling

    Returns:
        Generated text
    """
    # Tokenize input
    inputs = tokenizer(prompt, return_tensors="pt")

    # Move to same device as model
    device = next(model.parameters()).device
    inputs = {k: v.to(device) for k, v in inputs.items()}

    # Generate
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=top_p,
            do_sample=do_sample,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )

    # Decode
    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)

    # Remove the prompt from output
    if generated_text.startswith(prompt):
        generated_text = generated_text[len(prompt):].strip()

    return generated_text
