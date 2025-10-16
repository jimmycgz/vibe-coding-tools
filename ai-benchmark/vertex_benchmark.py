import anthropic
import time
import statistics
from typing import Dict, List

# Configure your Vertex AI settings
PROJECT_ID = "your-gcp-project"
REGION = "us-east5"

# Pricing per million tokens (Vertex AI pricing)
PRICING = {
    "claude-haiku-4-5@20251001": {
        "input": 1.00,   # $1.00 per million input tokens
        "output": 5.00   # $5.00 per million output tokens
    },
    "claude-sonnet-4-5@20250929": {
        "input": 3.00,   # $3.00 per million input tokens
        "output": 15.00  # $15.00 per million output tokens
    }
}

# Test prompts of varying complexity
TEST_PROMPTS = [
    "Write a haiku about coding.",
    "Explain quantum computing in simple terms.",
    "Write a detailed analysis of the benefits of functional programming vs object-oriented programming.",
    "Create a comprehensive guide to getting started with machine learning, including key concepts and practical steps."
]

# Max tokens configurations to test
MAX_TOKENS_CONFIGS = [256, 512]

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost of a request based on token usage."""
    pricing = PRICING.get(model, {"input": 0, "output": 0})
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return input_cost + output_cost

def benchmark_model(model: str, prompt: str, max_tokens: int, client: anthropic.AnthropicVertex) -> Dict:
    """Benchmark a single model with a given prompt."""
    start_time = time.time()
    
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    tokens_per_sec = output_tokens / elapsed if elapsed > 0 else 0
    cost = calculate_cost(model, input_tokens, output_tokens)
    
    return {
        "model": model,
        "max_tokens": max_tokens,
        "prompt_length": len(prompt),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "time_seconds": elapsed,
        "tokens_per_second": tokens_per_sec,
        "cost_usd": cost,
        "response_preview": response.content[0].text[:100] + "..."
    }

def run_benchmark(num_iterations: int = 3):
    """Run benchmark comparing Haiku 4.5 and Sonnet 4.5."""
    client = anthropic.AnthropicVertex(
        project_id=PROJECT_ID,
        region=REGION
    )
    
    models = [
        "claude-haiku-4-5@20251001",
        "claude-sonnet-4-5@20250929"
    ]
    
    results = {f"{model}_{max_tokens}": [] for model in models for max_tokens in MAX_TOKENS_CONFIGS}
    
    print("=" * 80)
    print("Claude Vertex AI Benchmark - Tokens/Second & Cost Comparison")
    print("=" * 80)
    print(f"\nRunning {num_iterations} iterations per prompt per model per max_tokens config...\n")
    
    for max_tokens in MAX_TOKENS_CONFIGS:
        print(f"\n{'=' * 80}")
        print(f"Testing with max_tokens={max_tokens}")
        print(f"{'=' * 80}")
        
        for i, prompt in enumerate(TEST_PROMPTS, 1):
            print(f"\n--- Test {i}: Prompt length {len(prompt)} chars ---")
            print(f"Prompt: {prompt[:60]}...")
            print()
            
            for model in models:
                model_name = "Haiku 4.5" if "haiku" in model else "Sonnet 4.5"
                print(f"Testing {model_name} (max_tokens={max_tokens})...")
                
                for iteration in range(num_iterations):
                    try:
                        result = benchmark_model(model, prompt, max_tokens, client)
                        results[f"{model}_{max_tokens}"].append(result)
                        print(f"  Iteration {iteration + 1}: {result['tokens_per_second']:.2f} tokens/s "
                              f"({result['output_tokens']} tokens in {result['time_seconds']:.2f}s, "
                              f"${result['cost_usd']:.6f})")
                    except Exception as e:
                        print(f"  Error: {e}")
                print()
    
    # Calculate and display summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    
    for max_tokens in MAX_TOKENS_CONFIGS:
        print(f"\n{'=' * 80}")
        print(f"max_tokens={max_tokens}")
        print(f"{'=' * 80}")
        
        for model in models:
            model_name = "Haiku 4.5" if "haiku" in model else "Sonnet 4.5"
            key = f"{model}_{max_tokens}"
            model_results = results[key]
            
            if not model_results:
                continue
            
            tokens_per_sec = [r['tokens_per_second'] for r in model_results]
            output_tokens = [r['output_tokens'] for r in model_results]
            times = [r['time_seconds'] for r in model_results]
            costs = [r['cost_usd'] for r in model_results]
            
            print(f"\n{model_name}:")
            print(f"  Average tokens/second: {statistics.mean(tokens_per_sec):.2f}")
            print(f"  Median tokens/second:  {statistics.median(tokens_per_sec):.2f}")
            print(f"  Min tokens/second:     {min(tokens_per_sec):.2f}")
            print(f"  Max tokens/second:     {max(tokens_per_sec):.2f}")
            if len(tokens_per_sec) > 1:
                print(f"  Std dev:               {statistics.stdev(tokens_per_sec):.2f}")
            print(f"  Avg output tokens:     {statistics.mean(output_tokens):.1f}")
            print(f"  Avg time:              {statistics.mean(times):.2f}s")
            print(f"  Avg cost per request:  ${statistics.mean(costs):.6f}")
            print(f"  Total cost:            ${sum(costs):.6f}")
    
    # Compare the models for each max_tokens configuration
    for max_tokens in MAX_TOKENS_CONFIGS:
        haiku_key = f"{models[0]}_{max_tokens}"
        sonnet_key = f"{models[1]}_{max_tokens}"
        
        if results[haiku_key] and results[sonnet_key]:
            haiku_avg = statistics.mean([r['tokens_per_second'] for r in results[haiku_key]])
            sonnet_avg = statistics.mean([r['tokens_per_second'] for r in results[sonnet_key]])
            haiku_cost = statistics.mean([r['cost_usd'] for r in results[haiku_key]])
            sonnet_cost = statistics.mean([r['cost_usd'] for r in results[sonnet_key]])
            
            print(f"\n" + "=" * 80)
            print(f"COMPARISON (max_tokens={max_tokens})")
            print("=" * 80)
            
            if haiku_avg > sonnet_avg:
                speedup = haiku_avg / sonnet_avg
                print(f"Haiku 4.5 is {speedup:.2f}x faster than Sonnet 4.5")
            else:
                speedup = sonnet_avg / haiku_avg
                print(f"Sonnet 4.5 is {speedup:.2f}x faster than Haiku 4.5")
            
            print(f"\nPerformance:")
            print(f"  Haiku avg:  {haiku_avg:.2f} tokens/s")
            print(f"  Sonnet avg: {sonnet_avg:.2f} tokens/s")
            
            print(f"\nCost per request:")
            print(f"  Haiku avg:  ${haiku_cost:.6f}")
            print(f"  Sonnet avg: ${sonnet_cost:.6f}")
            
            cost_ratio = sonnet_cost / haiku_cost if haiku_cost > 0 else 0
            print(f"  Sonnet is {cost_ratio:.2f}x more expensive than Haiku")

if __name__ == "__main__":
    # Update PROJECT_ID and REGION at the top of the file before running
    run_benchmark(num_iterations=3)
