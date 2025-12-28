"""
Local test harness for Parity - simulates the full flow without GitHub.

Usage:
    python -m src.test_harness                    # Test default file
    python -m src.test_harness prompts/test.txt   # Test specific file
    python -m src.test_harness --demo             # Force demo mode
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import DEMO_MODE, DIVERGENCE_THRESHOLD
from src.synthetic_generator import generate_adversarial_prompts
from src.judge import judge_prompt, output_json


def test_prompt_file(file_path: str, verbose: bool = True) -> dict:
    """
    Run full Parity analysis on a prompt file.
    
    Args:
        file_path: Path to the prompt file
        verbose: Whether to print progress
    
    Returns:
        Dict with results summary
    """
    if verbose:
        print("=" * 60)
        print("PARITY TEST HARNESS")
        print("=" * 60)
        print(f"Mode: {'DEMO (mock responses)' if DEMO_MODE else 'PRODUCTION (real API calls)'}")
        print(f"File: {file_path}")
        print(f"Threshold: {DIVERGENCE_THRESHOLD}")
        print()
    
    # Check file exists
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return {"error": "File not found", "passed": False}
    
    # Read prompt
    with open(file_path, 'r') as f:
        prompt_content = f.read()
    
    if verbose:
        print(f"📝 Prompt: {len(prompt_content)} characters")
        print()
    
    # Generate adversarial inputs
    if verbose:
        print("🧪 Generating adversarial test inputs...")
    
    test_inputs = generate_adversarial_prompts(prompt_content)
    
    if verbose:
        print(f"   Generated {len(test_inputs)} inputs")
        print()
        print("⚖️  Running divergence evaluation...")
        print()
    
    # Run evaluation
    results = []
    max_variance = 0.0
    
    for i, test_input in enumerate(test_inputs, 1):
        if verbose:
            # Truncate for display
            display_input = test_input[:60] + "..." if len(test_input) > 60 else test_input
            print(f"   [{i}/{len(test_inputs)}] {display_input}")
        
        try:
            result = judge_prompt(prompt_content, test_input)
            variance = result["variance"]
            max_variance = max(max_variance, variance)
            results.append(result)
            
            if verbose:
                icon = "✅" if variance < DIVERGENCE_THRESHOLD else "⚠️ "
                print(f"       {icon} Δ: {variance:.2f}")
                
                # Show pairwise breakdown
                if "metrics" in result and "pairwise" in result["metrics"]:
                    pairwise = result["metrics"]["pairwise"]
                    pairs = " | ".join([f"{k}: {v:.2f}" for k, v in pairwise.items()])
                    print(f"          [{pairs}]")
                print()
                
        except Exception as e:
            if verbose:
                print(f"       ❌ Error: {e}")
            results.append({
                "variance": 10.0,
                "error": str(e),
                "input": test_input
            })
            max_variance = max(max_variance, 10.0)
    
    # Calculate summary
    variances = [r.get("variance", 10.0) for r in results]
    avg_variance = sum(variances) / len(variances) if variances else 0.0
    passed = max_variance < DIVERGENCE_THRESHOLD
    
    summary = {
        "file": file_path,
        "passed": passed,
        "max_variance": round(max_variance, 2),
        "avg_variance": round(avg_variance, 2),
        "threshold": DIVERGENCE_THRESHOLD,
        "test_count": len(results),
        "demo_mode": DEMO_MODE
    }
    
    if verbose:
        print("=" * 60)
        print("📊 SUMMARY")
        print("=" * 60)
        print(f"Total tests:   {len(results)}")
        print(f"Max Δ:         {max_variance:.2f}")
        print(f"Avg Δ:         {avg_variance:.2f}")
        print(f"Threshold:     {DIVERGENCE_THRESHOLD}")
        print()
        
        if passed:
            print("✅ WOULD PASS - All divergence scores below threshold")
        else:
            print("❌ WOULD BLOCK - Divergence score exceeds threshold")
        
        print()
        print("=" * 60)
        print("📄 JSON Results:")
        print("=" * 60)
        print(output_json(results))
    
    return summary


def run_comparison_test(old_file: str, new_file: str) -> dict:
    """
    Compare two versions of a prompt file.
    
    Args:
        old_file: Path to the old/baseline prompt
        new_file: Path to the new prompt
    
    Returns:
        Comparison results
    """
    print("=" * 60)
    print("PARITY COMPARISON TEST")
    print("=" * 60)
    
    print(f"\n📁 Old: {old_file}")
    old_result = test_prompt_file(old_file, verbose=False)
    print(f"   Max Δ: {old_result.get('max_variance', 'N/A')}")
    
    print(f"\n📁 New: {new_file}")
    new_result = test_prompt_file(new_file, verbose=False)
    print(f"   Max Δ: {new_result.get('max_variance', 'N/A')}")
    
    print()
    print("=" * 60)
    print("📊 COMPARISON")
    print("=" * 60)
    
    old_var = old_result.get('max_variance', 0)
    new_var = new_result.get('max_variance', 0)
    delta = new_var - old_var
    
    print(f"Old Δ: {old_var:.2f}")
    print(f"New Δ: {new_var:.2f}")
    print(f"Delta: {delta:+.2f}")
    
    if delta > 0:
        print("\n⚠️  New prompt has HIGHER divergence (more model disagreement)")
    elif delta < 0:
        print("\n✅ New prompt has LOWER divergence (more model agreement)")
    else:
        print("\n➡️  No change in divergence")
    
    return {
        "old": old_result,
        "new": new_result,
        "delta": delta
    }


def main():
    """Main entry point for test harness."""
    parser = argparse.ArgumentParser(
        description="Parity Test Harness - Test prompt files locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.test_harness                         # Test default file
  python -m src.test_harness prompts/custom.txt      # Test specific file  
  python -m src.test_harness --demo                  # Force demo mode
  python -m src.test_harness --compare old.txt new.txt  # Compare two files
"""
    )
    
    parser.add_argument(
        "prompt_file",
        nargs="?",
        default="prompts/system.txt",
        help="Path to prompt file to test (default: prompts/system.txt)"
    )
    
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Force demo mode (mock API responses)"
    )
    
    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("OLD", "NEW"),
        help="Compare two prompt files"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON only"
    )
    
    args = parser.parse_args()
    
    # Set demo mode if requested
    if args.demo:
        os.environ["DEMO_MODE"] = "true"
        print("🎭 Running in DEMO MODE (mock API responses)")
        print()
    
    # Run appropriate test
    if args.compare:
        result = run_comparison_test(args.compare[0], args.compare[1])
        if args.json:
            print(json.dumps(result, indent=2))
    else:
        result = test_prompt_file(args.prompt_file, verbose=not args.json)
        if args.json:
            print(json.dumps(result, indent=2))
    
    # Return exit code based on result
    sys.exit(0 if result.get("passed", False) else 1)


if __name__ == "__main__":
    main()
