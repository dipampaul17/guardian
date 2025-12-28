#!/usr/bin/env python3
"""
False Positive Detection Experiment.

Tests adversarial inputs designed to trigger false positives in Guardian.
Supports binary classification and variance-based detection modes.
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import DEMO_MODE, VARIANCE_THRESHOLD, USE_BINARY_JUDGE, UNSAFE_VOTE_THRESHOLD
from src.judge import (
    judge_prompt, 
    get_model_responses, 
    calculate_triplicate_variance,
    triplicate_binary_judge
)


def load_adversarial_inputs(filepath: str) -> List[Dict[str, Any]]:
    """Load adversarial inputs from JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data['inputs']


def run_experiment(
    inputs: List[Dict[str, Any]],
    system_prompt: str,
    threshold: float = None,
    use_binary: bool = None
) -> Dict[str, Any]:
    """
    Run the false positive experiment.
    
    Args:
        inputs: List of adversarial input dicts
        system_prompt: The system prompt to test against
        threshold: Variance threshold (defaults to config) - only for legacy mode
        use_binary: Use binary classification mode (defaults to config)
    
    Returns:
        Experiment results
    """
    if threshold is None:
        threshold = VARIANCE_THRESHOLD
    if use_binary is None:
        use_binary = USE_BINARY_JUDGE
    
    results = []
    false_positives = []
    category_stats = defaultdict(lambda: {"total": 0, "false_positives": 0, "variances": [], "unsafe_votes": []})
    
    print("=" * 70)
    print("🧪 FALSE POSITIVE DETECTION EXPERIMENT")
    print("=" * 70)
    print(f"Mode: {'DEMO' if DEMO_MODE else 'PRODUCTION'}")
    print(f"Detection Method: {'BINARY CLASSIFICATION (LLM-as-Judge)' if use_binary else 'VARIANCE-BASED (Legacy)'}")
    if use_binary:
        print(f"Unsafe Vote Threshold: {UNSAFE_VOTE_THRESHOLD}/3 votes to block")
    else:
        print(f"Variance Threshold: {threshold}")
    print(f"Total Inputs: {len(inputs)}")
    print(f"System Prompt Length: {len(system_prompt)} chars")
    print()
    
    start_time = time.time()
    
    for i, input_data in enumerate(inputs, 1):
        input_id = input_data['id']
        category = input_data['category']
        user_input = input_data['input']
        predicted_reason = input_data['predicted_false_positive_reason']
        expected_variance = input_data['expected_variance']
        
        print(f"[{i:02d}/{len(inputs)}] ID={input_id} [{category}]")
        print(f"         Input: {user_input[:60]}...")
        
        try:
            judge_result = judge_prompt(system_prompt, user_input, use_binary=use_binary)
            responses = judge_result['responses']
            
            if use_binary:
                is_flagged = judge_result['is_unsafe']
                unsafe_votes = judge_result['unsafe_votes']
                safe_votes = judge_result['safe_votes']
                verdicts = judge_result.get('verdicts', {})
                
                result = {
                    "id": input_id,
                    "category": category,
                    "input": user_input,
                    "predicted_reason": predicted_reason,
                    "expected_variance": expected_variance,
                    "is_false_positive": is_flagged,
                    "unsafe_votes": unsafe_votes,
                    "safe_votes": safe_votes,
                    "verdicts": verdicts,
                    "judge_reason": judge_result.get('judge_reason', ''),
                    "responses": {k: v[:200] + "..." if len(v) > 200 else v for k, v in responses.items()}
                }
                
                category_stats[category]["unsafe_votes"].append(unsafe_votes)
                
                if is_flagged:
                    false_positives.append(result)
                    category_stats[category]["false_positives"] += 1
                    print(f"         ⚠️  FALSE POSITIVE! Votes: {unsafe_votes}/3 UNSAFE (threshold: {UNSAFE_VOTE_THRESHOLD})")
                else:
                    print(f"         ✅ Passed. Votes: {safe_votes}/3 SAFE, {unsafe_votes}/3 UNSAFE")
                
                verdict_str = " | ".join([f"{k}: {v.get('verdict', '?')}" for k, v in verdicts.items()])
                print(f"         Verdicts: [{verdict_str}]")
                
            else:
                max_variance = judge_result['variance']
                avg_variance = judge_result['avg_variance']
                metrics = judge_result['metrics']
                
                is_flagged = max_variance >= threshold
                
                result = {
                    "id": input_id,
                    "category": category,
                    "input": user_input,
                    "predicted_reason": predicted_reason,
                    "expected_variance": expected_variance,
                    "actual_max_variance": max_variance,
                    "actual_avg_variance": avg_variance,
                    "pairwise": metrics.get('pairwise', {}),
                    "is_false_positive": is_flagged,
                    "responses": {k: v[:200] + "..." if len(v) > 200 else v for k, v in responses.items()}
                }
                
                category_stats[category]["variances"].append(max_variance)
                
                if is_flagged:
                    false_positives.append(result)
                    category_stats[category]["false_positives"] += 1
                    print(f"         ⚠️  FALSE POSITIVE! Variance: {max_variance:.2f} (threshold: {threshold})")
                else:
                    print(f"         ✅ Passed. Variance: {max_variance:.2f}")
                
                pairwise = metrics.get('pairwise', {})
                pairwise_str = " | ".join([f"{k}: {v:.2f}" for k, v in pairwise.items()])
                print(f"         Pairwise: [{pairwise_str}]")
            
            results.append(result)
            category_stats[category]["total"] += 1
            print()
            
        except Exception as e:
            import traceback
            print(f"         ❌ Error: {e}")
            traceback.print_exc()
            results.append({
                "id": input_id,
                "category": category,
                "input": user_input,
                "error": str(e),
                "is_false_positive": True
            })
            category_stats[category]["total"] += 1
            category_stats[category]["false_positives"] += 1
            print()
        
        if not DEMO_MODE and i < len(inputs):
            time.sleep(0.5)
    
    elapsed = time.time() - start_time
    
    summary = {
        "timestamp": datetime.now().isoformat(),
        "mode": "DEMO" if DEMO_MODE else "PRODUCTION",
        "detection_method": "binary_classification" if use_binary else "variance",
        "threshold": UNSAFE_VOTE_THRESHOLD if use_binary else threshold,
        "total_inputs": len(inputs),
        "total_false_positives": len(false_positives),
        "false_positive_rate": len(false_positives) / len(inputs) * 100 if inputs else 0,
        "elapsed_seconds": round(elapsed, 2),
        "by_category": {},
        "by_expected_variance": defaultdict(lambda: {"total": 0, "false_positives": 0})
    }
    
    if use_binary:
        all_unsafe_votes = [r.get('unsafe_votes', 0) for r in results if 'unsafe_votes' in r]
        summary["vote_stats"] = {
            "max_unsafe_votes": max(all_unsafe_votes) if all_unsafe_votes else 0,
            "avg_unsafe_votes": round(sum(all_unsafe_votes) / len(all_unsafe_votes), 2) if all_unsafe_votes else 0,
        }
    else:
        all_variances = [r.get('actual_max_variance', 0) for r in results if 'actual_max_variance' in r]
        summary["variance_stats"] = {
            "max": round(max(all_variances), 2) if all_variances else 0,
            "min": round(min(all_variances), 2) if all_variances else 0,
            "avg": round(sum(all_variances) / len(all_variances), 2) if all_variances else 0
        }
    
    for cat, stats in category_stats.items():
        cat_summary = {
            "total": stats["total"],
            "false_positives": stats["false_positives"],
            "fp_rate": round(stats["false_positives"] / stats["total"] * 100, 1) if stats["total"] else 0,
        }
        if use_binary and stats["unsafe_votes"]:
            cat_summary["avg_unsafe_votes"] = round(sum(stats["unsafe_votes"]) / len(stats["unsafe_votes"]), 2)
        elif stats["variances"]:
            cat_summary["avg_variance"] = round(sum(stats["variances"]) / len(stats["variances"]), 2)
        summary["by_category"][cat] = cat_summary
    
    for result in results:
        exp_var = result.get('expected_variance', 'unknown')
        summary["by_expected_variance"][exp_var]["total"] += 1
        if result.get('is_false_positive', False):
            summary["by_expected_variance"][exp_var]["false_positives"] += 1
    
    return {
        "summary": summary,
        "results": results,
        "false_positives": false_positives
    }


def print_summary(experiment_results: Dict[str, Any]):
    """Print experiment summary."""
    summary = experiment_results['summary']
    false_positives = experiment_results['false_positives']
    is_binary = summary.get('detection_method') == 'binary_classification'
    
    print("=" * 70)
    print("📊 EXPERIMENT SUMMARY")
    print("=" * 70)
    print()
    print(f"Detection Method:    {'BINARY CLASSIFICATION' if is_binary else 'VARIANCE-BASED'}")
    print(f"Total Inputs:        {summary['total_inputs']}")
    print(f"False Positives:     {summary['total_false_positives']}")
    print(f"False Positive Rate: {summary['false_positive_rate']:.1f}%")
    print(f"Elapsed Time:        {summary['elapsed_seconds']:.1f}s")
    print()
    
    if is_binary:
        print("🗳️ Vote Statistics:")
        vote_stats = summary.get('vote_stats', {})
        print(f"   Max Unsafe Votes: {vote_stats.get('max_unsafe_votes', 0)}/3")
        print(f"   Avg Unsafe Votes: {vote_stats.get('avg_unsafe_votes', 0):.2f}/3")
        print(f"   Block Threshold:  {summary['threshold']}/3 votes")
    else:
        print("📈 Variance Statistics:")
        var_stats = summary.get('variance_stats', {})
        print(f"   Max: {var_stats.get('max', 0):.2f}")
        print(f"   Min: {var_stats.get('min', 0):.2f}")
        print(f"   Avg: {var_stats.get('avg', 0):.2f}")
    print()
    
    print("📂 By Category:")
    print("-" * 50)
    for cat, stats in sorted(summary['by_category'].items()):
        print(f"   {cat}:")
        print(f"      Total: {stats['total']} | FP: {stats['false_positives']} ({stats['fp_rate']:.1f}%)")
        if is_binary and 'avg_unsafe_votes' in stats:
            print(f"      Avg Unsafe Votes: {stats['avg_unsafe_votes']:.2f}/3")
        elif 'avg_variance' in stats:
            print(f"      Avg Variance: {stats['avg_variance']:.2f}")
    print()
    
    print("📊 By Expected Variance Level:")
    print("-" * 50)
    for level in ['high', 'medium', 'low']:
        if level in summary['by_expected_variance']:
            stats = summary['by_expected_variance'][level]
            fp_rate = stats['false_positives'] / stats['total'] * 100 if stats['total'] else 0
            print(f"   {level.upper():8s}: {stats['total']:2d} inputs, {stats['false_positives']:2d} FPs ({fp_rate:.1f}%)")
    print()
    
    if false_positives:
        print("=" * 70)
        print("🚨 FALSE POSITIVES DETAILS")
        print("=" * 70)
        for fp in false_positives[:10]:  # Limit to first 10
            print()
            print(f"ID: {fp['id']} | Category: {fp['category']}")
            print(f"Input: {fp['input'][:80]}...")
            if is_binary:
                print(f"Unsafe Votes: {fp.get('unsafe_votes', 'N/A')}/3")
                if 'verdicts' in fp:
                    for judge, verdict in fp['verdicts'].items():
                        print(f"   {judge}: {verdict.get('verdict', '?')} - {verdict.get('reason', '')[:60]}...")
            else:
                print(f"Variance: {fp.get('actual_max_variance', 'N/A')}")
                if 'pairwise' in fp:
                    print(f"Pairwise: {fp['pairwise']}")
            print(f"Predicted Reason: {fp.get('predicted_reason', 'N/A')[:80]}...")
        
        if len(false_positives) > 10:
            print(f"\n... and {len(false_positives) - 10} more false positives")


def main():
    """Run the experiment."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Run False Positive Detection Experiment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with new binary classification (default)
  python run_false_positive_experiment.py
  
  # Run with legacy variance-based detection
  python run_false_positive_experiment.py --variance
  
  # Compare both methods
  python run_false_positive_experiment.py --limit 10
  python run_false_positive_experiment.py --limit 10 --variance
"""
    )
    parser.add_argument(
        "--inputs",
        default="tests/adversarial_false_positive_inputs.json",
        help="Path to adversarial inputs JSON file"
    )
    parser.add_argument(
        "--prompt",
        default="prompts/system.txt",
        help="Path to system prompt file"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help=f"Variance threshold for legacy mode (default: {VARIANCE_THRESHOLD})"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file for full results JSON"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of inputs to test"
    )
    parser.add_argument(
        "--binary",
        action="store_true",
        default=None,
        help="Use binary classification mode (LLM-as-judge) - DEFAULT"
    )
    parser.add_argument(
        "--variance",
        action="store_true",
        help="Use legacy variance-based detection mode"
    )
    
    args = parser.parse_args()
    
    if args.variance:
        use_binary = False
    elif args.binary:
        use_binary = True
    else:
        use_binary = USE_BINARY_JUDGE
    
    inputs_path = Path(args.inputs)
    if not inputs_path.is_absolute():
        inputs_path = Path(__file__).parent.parent / inputs_path
    
    print(f"Loading inputs from: {inputs_path}")
    inputs = load_adversarial_inputs(str(inputs_path))
    
    if args.limit:
        inputs = inputs[:args.limit]
        print(f"Limited to first {args.limit} inputs")
    
    prompt_path = Path(args.prompt)
    if not prompt_path.is_absolute():
        prompt_path = Path(__file__).parent.parent / prompt_path
    
    print(f"Loading prompt from: {prompt_path}")
    with open(prompt_path, 'r') as f:
        system_prompt = f.read()
    
    print()
    
    results = run_experiment(inputs, system_prompt, args.threshold, use_binary=use_binary)
    print_summary(results)
    
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mode_suffix = "binary" if use_binary else "variance"
        output_dir = Path(__file__).parent.parent / "experiments" / "results"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"false_positive_experiment_{mode_suffix}_{timestamp}.json"
    
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print()
    print(f"📁 Full results saved to: {output_path}")
    
    fp_rate = results['summary']['false_positive_rate']
    if fp_rate > 50:
        print("\n❌ HIGH false positive rate detected - system needs tuning!")
        return 1
    elif fp_rate > 25:
        print("\n⚠️  MODERATE false positive rate - consider threshold adjustment")
        return 0
    else:
        print("\n✅ LOW false positive rate - system performing well")
        return 0


if __name__ == "__main__":
    sys.exit(main())
