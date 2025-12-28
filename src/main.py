"""Main orchestrator for Parity divergence detection."""
import os
import sys
import json
import time
import subprocess
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from github import Github

from src.config import (
    DIVERGENCE_THRESHOLD,
    DEMO_MODE,
    GITHUB_TOKEN,
    MAX_RETRIES,
    NUM_SYNTHETIC_INPUTS,
)
from src.synthetic_generator import generate_adversarial_prompts
from src.judge import judge_prompt, output_json


def get_changed_prompt_files(pr) -> List[str]:
    """
    Get list of changed prompt files from PR.
    
    Args:
        pr: GitHub PullRequest object
    
    Returns:
        List of prompt file paths that were modified
    """
    prompt_files = []
    for file in pr.get_files():
        # Match files in prompts/ directory with .txt extension
        if file.filename.startswith("prompts/") and file.filename.endswith(".txt"):
            prompt_files.append(file.filename)
    return prompt_files


def get_baseline_content(file_path: str, target_branch: str) -> str:
    """
    Get file content from the base branch using git show.
    
    Args:
        file_path: Path to the file
        target_branch: Base branch name (e.g., 'main')
    
    Returns:
        File content as string, or empty string if file doesn't exist
    """
    try:
        cmd = ["git", "show", f"origin/{target_branch}:{file_path}"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError:
        # File doesn't exist in base branch (new file)
        return ""


def get_current_content(file_path: str) -> str:
    """
    Get current file content from disk.
    
    Args:
        file_path: Path to the file
    
    Returns:
        File content as string
    
    Raises:
        FileNotFoundError: If file doesn't exist
    """
    with open(file_path, 'r') as f:
        return f.read()


def save_audit_report(results: Dict[str, Any], pr_number: int, repo_name: str) -> str:
    """
    Save audit report to file and return path.
    
    Args:
        results: Audit results dictionary
        pr_number: PR number
        repo_name: Repository name
    
    Returns:
        Path to saved audit file
    """
    audit_dir = Path("audit")
    audit_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"parity_pr{pr_number}_{timestamp}.json"
    filepath = audit_dir / filename
    
    audit_data = {
        "timestamp": datetime.now().isoformat(),
        "repository": repo_name,
        "pr_number": pr_number,
        "threshold": DIVERGENCE_THRESHOLD,
        "demo_mode": DEMO_MODE,
        **results
    }
    
    with open(filepath, 'w') as f:
        json.dump(audit_data, f, indent=2, default=str)
    
    print(f"📁 Audit report saved: {filepath}")
    return str(filepath)


def post_pr_comment(pr, status: str, max_variance: float, details: str = ""):
    """
    Post a Parity status comment to the PR.
    
    Args:
        pr: GitHub PullRequest object
        status: Status string (PASSED, BLOCKED, etc.)
        max_variance: Maximum divergence score detected
        details: Additional details to include
    """
    emoji = "✅" if "PASS" in status or "APPROVE" in status or "OVERRIDE" in status else "❌"
    
    comment = f"""## Parity Divergence Check

**Status:** {emoji} {status}
**Max Divergence (Δ):** {max_variance:.2f} / 10
**Threshold:** {DIVERGENCE_THRESHOLD}
**Mode:** {"DEMO" if DEMO_MODE else "PRODUCTION"}

{details}

---
*To bypass this check, an authorized reviewer can comment:* `/parity override [reason]`
"""
    
    pr.create_issue_comment(comment)


def run_parity() -> int:
    """
    Main Parity execution function.
    
    Returns:
        Exit code: 0 for pass, 1 for block/error
    """
    print("=" * 60)
    print("PARITY DIVERGENCE CHECK")
    print("=" * 60)
    print(f"Mode: {'DEMO (3 prompts, mock responses)' if DEMO_MODE else 'PRODUCTION (20 prompts, real API calls)'}")
    print(f"Divergence Threshold: {DIVERGENCE_THRESHOLD}")
    print()
    
    try:
        # =========================================================
        # 1. SETUP - Get GitHub context
        # =========================================================
        token = GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GITHUB_TOKEN not set")
        
        repo_name = os.getenv("GITHUB_REPOSITORY")
        if not repo_name:
            raise ValueError("GITHUB_REPOSITORY not set")
        
        github = Github(token)
        repo = github.get_repo(repo_name)
        
        # Get PR number from GITHUB_REF (format: refs/pull/123/merge)
        github_ref = os.getenv("GITHUB_REF", "")
        if not github_ref.startswith("refs/pull/"):
            raise ValueError(f"Invalid GITHUB_REF format: {github_ref}. Expected refs/pull/N/merge")
        
        pr_number = int(github_ref.split('/')[2])
        pr = repo.get_pull(pr_number)
        target_branch = os.getenv("GITHUB_BASE_REF", "main")
        
        print(f"📋 PR #{pr_number}: {pr.title}")
        print(f"🎯 Target branch: {target_branch}")
        print()
        
        # =========================================================
        # 2. OVERRIDE CHECK - Check for /parity override FIRST
        # =========================================================
        print("🔍 Checking for override comments...")
        
        # Check PR body
        if pr.body and "/parity override" in pr.body.lower():
            print("✅ Override found in PR description")
            post_pr_comment(pr, "OVERRIDDEN", 0.0, "Override found in PR description.")
            return 0
        
        # Check issue comments
        for comment in pr.get_issue_comments():
            if "/parity override" in comment.body.lower():
                print(f"✅ Override found in comment by @{comment.user.login}")
                post_pr_comment(pr, "OVERRIDDEN", 0.0, f"Override by @{comment.user.login}")
                return 0
        
        print("   No override found, proceeding with analysis...")
        print()
        
        # =========================================================
        # 3. DETECT CHANGED PROMPT FILES
        # =========================================================
        print("📂 Detecting changed prompt files...")
        changed_files = get_changed_prompt_files(pr)
        
        if not changed_files:
            print("   No prompt files changed in this PR")
            post_pr_comment(pr, "NO CHANGES", 0.0, "No prompt files were modified in this PR.")
            return 0
        
        print(f"   Found {len(changed_files)} changed prompt file(s):")
        for f in changed_files:
            print(f"   - {f}")
        print()
        
        # =========================================================
        # 4. ANALYZE EACH CHANGED PROMPT FILE
        # =========================================================
        all_results = []
        overall_max_variance = 0.0
        
        for prompt_file in changed_files:
            print(f"{'='*60}")
            print(f"📝 Analyzing: {prompt_file}")
            print(f"{'='*60}")
            
            # Get baseline (from target branch)
            baseline_content = get_baseline_content(prompt_file, target_branch)
            if not baseline_content:
                print(f"   ℹ️  New file (no baseline in {target_branch})")
            
            # Get current content
            try:
                new_content = get_current_content(prompt_file)
            except FileNotFoundError:
                print(f"   ⚠️  File not found on disk, skipping")
                continue
            
            # Check if content actually changed
            if baseline_content == new_content:
                print(f"   ℹ️  No content changes detected, skipping")
                continue
            
            print(f"   Baseline: {len(baseline_content)} chars")
            print(f"   New:      {len(new_content)} chars")
            print()
            
            # Generate adversarial test inputs
            print("🧪 Generating adversarial test inputs...")
            test_inputs = generate_adversarial_prompts(new_content)
            print(f"   Generated {len(test_inputs)} test inputs")
            print()
            
            # Run divergence evaluation on each input
            print("⚖️  Running divergence evaluation...")
            file_results = []
            file_max_variance = 0.0
            
            for i, test_input in enumerate(test_inputs, 1):
                print(f"   [{i}/{len(test_inputs)}] Testing: {test_input[:50]}...")
                
                # Add retry logic with rate limiting
                for attempt in range(MAX_RETRIES):
                    try:
                        result = judge_prompt(new_content, test_input)
                        variance = result["variance"]
                        file_max_variance = max(file_max_variance, variance)
                        file_results.append(result)
                        
                        status_icon = "✅" if variance < DIVERGENCE_THRESHOLD else "⚠️"
                        print(f"       {status_icon} Δ: {variance:.2f}")
                        break
                    except Exception as e:
                        if attempt < MAX_RETRIES - 1:
                            print(f"       ⚠️  Retry {attempt + 1}/{MAX_RETRIES}: {e}")
                            time.sleep(1.0)  # Rate limit protection
                        else:
                            print(f"       ❌ Failed after {MAX_RETRIES} attempts: {e}")
                            file_results.append({
                                "variance": 10.0,
                                "error": str(e),
                                "input": test_input
                            })
                            file_max_variance = max(file_max_variance, 10.0)
                
                # Rate limiting between requests
                if i < len(test_inputs):
                    time.sleep(0.5)
            
            overall_max_variance = max(overall_max_variance, file_max_variance)
            
            all_results.append({
                "file": prompt_file,
                "max_variance": file_max_variance,
                "test_count": len(file_results),
                "results": file_results
            })
            
            print()
            print(f"   📊 File Max Δ: {file_max_variance:.2f}")
            print()
        
        # =========================================================
        # 5. MAKE DECISION
        # =========================================================
        print("=" * 60)
        print("📊 FINAL RESULTS")
        print("=" * 60)
        print(f"Overall Max Δ: {overall_max_variance:.2f}")
        print(f"Threshold: {DIVERGENCE_THRESHOLD}")
        print()
        
        if overall_max_variance < DIVERGENCE_THRESHOLD:
            status = "AUTO-APPROVED"
            print("✅ PASSED - All divergence scores below threshold")
            exit_code = 0
        else:
            status = "BLOCKED"
            print("❌ BLOCKED - Divergence score exceeds threshold")
            print("   A reviewer must comment '/parity override [reason]' to proceed")
            exit_code = 1
        
        # =========================================================
        # 6. SAVE AUDIT & POST COMMENT
        # =========================================================
        audit_data = {
            "status": status,
            "max_variance": overall_max_variance,
            "files_analyzed": len(all_results),
            "file_results": all_results
        }
        
        audit_path = save_audit_report(audit_data, pr_number, repo_name)
        
        # Build details for PR comment
        details_lines = ["### Files Analyzed:"]
        for file_result in all_results:
            icon = "✅" if file_result["max_variance"] < DIVERGENCE_THRESHOLD else "⚠️"
            details_lines.append(f"- {icon} `{file_result['file']}` — Δ: {file_result['max_variance']:.2f}")
        
        details = "\n".join(details_lines)
        post_pr_comment(pr, status, overall_max_variance, details)
        
        print()
        print(f"🏁 Parity complete. Exit code: {exit_code}")
        return exit_code
        
    except Exception as e:
        # =========================================================
        # ERROR HANDLING - Log crash to PR
        # =========================================================
        error_msg = f"Parity crashed: {str(e)}"
        print(f"\n❌ ERROR: {error_msg}", file=sys.stderr)
        print(traceback.format_exc(), file=sys.stderr)
        
        # Try to post error to PR
        try:
            repo_name = os.getenv("GITHUB_REPOSITORY")
            github_ref = os.getenv("GITHUB_REF", "")
            token = GITHUB_TOKEN or os.getenv("GITHUB_TOKEN")
            
            if repo_name and github_ref.startswith("refs/pull/") and token:
                pr_number = int(github_ref.split('/')[2])
                github = Github(token)
                repo = github.get_repo(repo_name)
                pr = repo.get_pull(pr_number)
                
                error_comment = f"""## Parity Divergence Check

**Status:** ❌ ERROR

```
{error_msg}

{traceback.format_exc()}
```

Please check the action logs for details.
"""
                pr.create_issue_comment(error_comment)
        except Exception as post_error:
            print(f"Failed to post error to PR: {post_error}", file=sys.stderr)
        
        return 1


def run_local(prompt_file: str = "prompts/system.txt") -> int:
    """
    Run Parity locally without GitHub context.
    
    Args:
        prompt_file: Path to prompt file to test
    
    Returns:
        Exit code: 0 for pass, 1 for fail
    """
    print("=" * 60)
    print("PARITY DIVERGENCE CHECK (LOCAL MODE)")
    print("=" * 60)
    print(f"Mode: {'DEMO' if DEMO_MODE else 'PRODUCTION'}")
    print(f"File: {prompt_file}")
    print(f"Threshold: {DIVERGENCE_THRESHOLD}")
    print()
    
    # Read prompt file
    try:
        with open(prompt_file, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ File not found: {prompt_file}")
        return 1
    
    print(f"📝 Prompt length: {len(content)} characters")
    print()
    
    # Generate test inputs
    print("🧪 Generating adversarial inputs...")
    test_inputs = generate_adversarial_prompts(content)
    print(f"   Generated {len(test_inputs)} inputs")
    print()
    
    # Run divergence evaluation
    print("⚖️  Running divergence evaluation...")
    results = []
    max_variance = 0.0
    
    for i, test_input in enumerate(test_inputs, 1):
        print(f"   [{i}/{len(test_inputs)}] {test_input[:50]}...")
        
        try:
            result = judge_prompt(content, test_input)
            variance = result["variance"]
            max_variance = max(max_variance, variance)
            results.append(result)
            
            icon = "✅" if variance < DIVERGENCE_THRESHOLD else "⚠️"
            print(f"       {icon} Δ: {variance:.2f}")
        except Exception as e:
            print(f"       ❌ Error: {e}")
            results.append({"variance": 10.0, "error": str(e), "input": test_input})
            max_variance = max(max_variance, 10.0)
    
    # Results
    print()
    print("=" * 60)
    print("📊 RESULTS")
    print("=" * 60)
    print(f"Max Δ: {max_variance:.2f}")
    print(f"Threshold: {DIVERGENCE_THRESHOLD}")
    print()
    
    if max_variance < DIVERGENCE_THRESHOLD:
        print("✅ WOULD PASS")
        exit_code = 0
    else:
        print("❌ WOULD BLOCK")
        exit_code = 1
    
    # Output JSON
    print()
    print("📄 JSON Results:")
    print(output_json(results))
    
    return exit_code


if __name__ == "__main__":
    # Check if running in GitHub Actions context
    if os.getenv("GITHUB_ACTIONS") == "true":
        exit_code = run_parity()
    else:
        # Local mode - use command line arg or default
        import argparse
        parser = argparse.ArgumentParser(description="Parity Divergence Check")
        parser.add_argument("prompt_file", nargs="?", default="prompts/system.txt",
                          help="Path to prompt file to test (local mode)")
        args = parser.parse_args()
        exit_code = run_local(args.prompt_file)
    
    sys.exit(exit_code)
