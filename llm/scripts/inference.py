"""
Inference Script for MLB Best Ball LLM

Provides:
1. Interactive CLI chat
2. API endpoint for web app integration
3. Single query function
"""

import torch
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

# Paths
SCRIPT_DIR = Path(__file__).parent
LLM_DIR = SCRIPT_DIR.parent
OUTPUT_DIR = LLM_DIR / 'output'
MODELS_DIR = LLM_DIR / 'models'

# Model paths (in order of preference)
MODEL_PATHS = [
    MODELS_DIR / 'mlb_bestball_merged',     # Merged model (fastest)
    OUTPUT_DIR / 'final_model',              # LoRA adapter
]

BASE_MODEL = "mistralai/Mistral-7B-Instruct-v0.2"

# System prompt for the baseball assistant
SYSTEM_PROMPT = """You are an expert MLB fantasy baseball assistant specializing in best ball formats, particularly NFBC Cutline Championship. You have deep knowledge of:
- Cutline scoring rules and strategy
- Player rankings and projections
- Draft strategy and roster construction
- Baseball statistics and analytics
Provide helpful, accurate advice to help users win their best ball leagues."""


class MLBBestBallLLM:
    """MLB Best Ball Assistant powered by fine-tuned LLM."""

    def __init__(self, model_path=None, use_4bit=True):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = None
        self.tokenizer = None
        self.model_path = model_path
        self.use_4bit = use_4bit

        self._load_model()

    def _find_model(self):
        """Find the best available model."""
        if self.model_path:
            return Path(self.model_path)

        for path in MODEL_PATHS:
            if path.exists():
                return path

        return None

    def _load_model(self):
        """Load the fine-tuned model."""
        model_path = self._find_model()

        if model_path is None:
            print("No fine-tuned model found. Using base model.")
            print("Run finetune.py to train a custom model!")
            model_path = None
            is_merged = False
        else:
            print(f"Loading model from: {model_path}")
            # Check if it's a merged model or LoRA adapter
            is_merged = (model_path / 'config.json').exists() and not (model_path / 'adapter_config.json').exists()

        # Quantization for 16GB VRAM
        if self.use_4bit:
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
            )
        else:
            bnb_config = None

        if model_path and is_merged:
            # Load merged model directly
            self.model = AutoModelForCausalLM.from_pretrained(
                str(model_path),
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
            )
            self.tokenizer = AutoTokenizer.from_pretrained(str(model_path))
        else:
            # Load base model
            self.model = AutoModelForCausalLM.from_pretrained(
                BASE_MODEL,
                quantization_config=bnb_config,
                device_map="auto",
                trust_remote_code=True,
            )
            self.tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

            # Apply LoRA adapter if available
            if model_path and (model_path / 'adapter_config.json').exists():
                print("Loading LoRA adapter...")
                self.model = PeftModel.from_pretrained(self.model, str(model_path))

        self.tokenizer.pad_token = self.tokenizer.eos_token
        print("Model loaded successfully!")

    def generate(self, prompt, max_new_tokens=512, temperature=0.7, top_p=0.9):
        """Generate a response to a prompt."""
        # Format for Mistral
        full_prompt = f"<s>[INST] {SYSTEM_PROMPT}\n\n{prompt} [/INST]"

        inputs = self.tokenizer(full_prompt, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=True,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)

        # Extract just the assistant's response
        if "[/INST]" in response:
            response = response.split("[/INST]")[-1].strip()

        return response

    def chat(self, message, history=None):
        """Chat with context from previous messages."""
        if history is None:
            history = []

        # Build conversation context
        context = SYSTEM_PROMPT + "\n\n"
        for user_msg, assistant_msg in history[-5:]:  # Last 5 turns
            context += f"User: {user_msg}\nAssistant: {assistant_msg}\n\n"
        context += f"User: {message}\nAssistant:"

        response = self.generate(context)
        return response


def interactive_chat():
    """Run interactive CLI chat."""
    print("=" * 60)
    print("MLB Best Ball Assistant")
    print("=" * 60)
    print("\nLoading model (this may take a minute)...")

    llm = MLBBestBallLLM()

    print("\n" + "=" * 60)
    print("Chat started! Type 'quit' to exit.")
    print("=" * 60 + "\n")

    history = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ['quit', 'exit', 'q']:
            print("Goodbye!")
            break

        print("\nAssistant: ", end="", flush=True)
        response = llm.chat(user_input, history)
        print(response)
        print()

        history.append((user_input, response))


def create_api_handler():
    """Create a handler function for web API integration."""
    llm = None

    def handler(message, history=None):
        nonlocal llm
        if llm is None:
            llm = MLBBestBallLLM()
        return llm.chat(message, history)

    return handler


# Flask API for web integration
def create_flask_api():
    """Create Flask API for the LLM."""
    from flask import Flask, request, jsonify

    app = Flask(__name__)
    llm = None

    @app.route('/api/chat', methods=['POST'])
    def chat():
        nonlocal llm
        if llm is None:
            llm = MLBBestBallLLM()

        data = request.json
        message = data.get('message', '')
        history = data.get('history', [])

        if not message:
            return jsonify({'error': 'No message provided'}), 400

        response = llm.chat(message, history)
        return jsonify({'response': response})

    @app.route('/api/health', methods=['GET'])
    def health():
        return jsonify({'status': 'ok'})

    return app


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='MLB Best Ball LLM Inference')
    parser.add_argument('--api', action='store_true', help='Run as Flask API server')
    parser.add_argument('--port', type=int, default=5001, help='API server port')
    parser.add_argument('--query', type=str, help='Single query mode')
    args = parser.parse_args()

    if args.api:
        print("Starting LLM API server...")
        app = create_flask_api()
        app.run(host='0.0.0.0', port=args.port, debug=False)
    elif args.query:
        llm = MLBBestBallLLM()
        print(llm.generate(args.query))
    else:
        interactive_chat()
