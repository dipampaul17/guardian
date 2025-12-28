"""GitHub client for handling PR comments and status checks."""
import os
import json
from typing import Optional, List, Dict, Any
from github import Github
from github.PullRequest import PullRequest


def post_pr_comment(pr_number: int, status: str, score: float, audit_url: str):
    """
    Post a Guardian Safety Gate comment to a PR.
    
    Args:
        pr_number: Pull request number
        status: Status string (e.g., "PASSED", "BLOCKED")
        score: Variance score (0-10)
        audit_url: URL to audit report
    """
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("GITHUB_TOKEN not set")
    
    repo_name = os.getenv("GITHUB_REPOSITORY")
    if not repo_name:
        raise ValueError("GITHUB_REPOSITORY not set")
    
    github = Github(token)
    repo = github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    
    message = f"""## Guardian Safety Gate
**Status:** {status}
**Variance Score:** {score}/10
**Audit:** [Link]({audit_url})
**Action:** To bypass, comment `/guardian override [reason]`"""
    
    pr.create_issue_comment(message)


class GitHubClient:
    """Wrapper for GitHub API operations."""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError("GITHUB_TOKEN not set")
        self.github = Github(self.token)
        self.repo = None
        self.pr = None
    
    def initialize_repo(self, repo_name: Optional[str] = None):
        """Initialize repository from environment or parameter."""
        repo_name = repo_name or os.getenv("GITHUB_REPOSITORY")
        if not repo_name:
            raise ValueError("GITHUB_REPOSITORY not set")
        self.repo = self.github.get_repo(repo_name)
    
    def get_pr(self, pr_number: Optional[int] = None) -> PullRequest:
        """Get PR from event or by number."""
        if self.pr:
            return self.pr
        
        if pr_number:
            self.pr = self.repo.get_pull(pr_number)
            return self.pr
        
        # Try to get from GitHub Actions event
        event_path = os.getenv("GITHUB_EVENT_PATH")
        if event_path and os.path.exists(event_path):
            try:
                with open(event_path, 'r') as f:
                    event_data = json.load(f)
                    pr_number = event_data.get("pull_request", {}).get("number")
                    if pr_number:
                        self.pr = self.repo.get_pull(pr_number)
                        return self.pr
            except (json.JSONDecodeError, KeyError, Exception) as e:
                print(f"Warning: Could not parse event file: {e}")
        
        # Fallback: try GITHUB_REF (format: refs/pull/123/merge)
        ref = os.getenv("GITHUB_REF", "")
        if ref.startswith("refs/pull/"):
            try:
                pr_number = int(ref.split("/")[2])
                self.pr = self.repo.get_pull(pr_number)
                return self.pr
            except (ValueError, IndexError):
                pass
        
        raise ValueError("Could not determine PR number")
    
    def check_for_override(self, pr: Optional[PullRequest] = None) -> bool:
        """
        Check if PR has override comment.
        
        Args:
            pr: PullRequest object (optional, will fetch if not provided)
        
        Returns:
            True if override comment found, False otherwise
        """
        from src.config import OVERRIDE_COMMAND
        
        if not pr:
            pr = self.get_pr()
        
        # Check PR body (handle None)
        if pr.body and OVERRIDE_COMMAND.lower() in pr.body.lower():
            return True
        
        # Check comments
        comments = pr.get_issue_comments()
        for comment in comments:
            if OVERRIDE_COMMAND.lower() in comment.body.lower():
                return True
        
        # Check review comments
        review_comments = pr.get_review_comments()
        for comment in review_comments:
            if OVERRIDE_COMMAND.lower() in comment.body.lower():
                return True
        
        return False
    
    def get_changed_prompt_files(self, pr: Optional[PullRequest] = None) -> List[str]:
        """
        Get list of changed prompt files in PR.
        
        Args:
            pr: PullRequest object (optional)
        
        Returns:
            List of file paths
        """
        if not pr:
            pr = self.get_pr()
        
        files = pr.get_files()
        prompt_files = []
        
        for file in files:
            if file.filename.endswith('.txt') and 'prompts' in file.filename:
                prompt_files.append(file.filename)
        
        return prompt_files
    
    def get_file_content(self, file_path: str, ref: Optional[str] = None) -> str:
        """
        Get file content from repository.
        
        Args:
            file_path: Path to file
            ref: Git reference (branch/tag/commit), defaults to PR head
        
        Returns:
            File content as string
        """
        if not ref:
            pr = self.get_pr()
            ref = pr.head.sha
        
        content = self.repo.get_contents(file_path, ref=ref)
        if isinstance(content, list):
            raise ValueError(f"{file_path} is a directory, not a file")
        
        import base64
        return base64.b64decode(content.content).decode('utf-8')
    
    def post_comment(self, message: str, pr: Optional[PullRequest] = None):
        """Post a comment on the PR."""
        if not pr:
            pr = self.get_pr()
        
        pr.create_issue_comment(message)
    
    def approve_and_merge(self, pr: Optional[PullRequest] = None):
        """Approve and merge PR (for override case)."""
        if not pr:
            pr = self.get_pr()
        
        # Approve PR
        pr.create_review(event="APPROVE", body="Guardian override approved")
        
        # Merge PR
        pr.merge(commit_message="Merged via Guardian override")
    
    def block_pr(self, reason: str, pr: Optional[PullRequest] = None):
        """
        Block PR by posting a comment and requesting changes.
        
        Args:
            reason: Reason for blocking
            pr: PullRequest object (optional)
        """
        if not pr:
            pr = self.get_pr()
        
        message = f"🚫 **Guardian Safety Gate: BLOCKED**\n\n{reason}\n\nPlease review and fix the issues before merging."
        self.post_comment(message, pr)
        
        # Request changes
        pr.create_review(
            event="REQUEST_CHANGES",
            body=message
        )
    
    def approve_pr(self, message: str, pr: Optional[PullRequest] = None):
        """Approve PR with a message."""
        if not pr:
            pr = self.get_pr()
        
        pr.create_review(event="APPROVE", body=message)
