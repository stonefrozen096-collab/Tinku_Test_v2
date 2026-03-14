"""
GitHub Agent — Analyze repos, check commits, suggest improvements, generate README.
"""
import os
import aiohttp
from .base_agent import BaseAgent
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from providers import generate_response


class GitHubAgent(BaseAgent):
    def __init__(self):
        super().__init__("GitHubAgent", "🐙", "Analyze repos, commits, generate README")
        self.token = os.getenv("GITHUB_TOKEN", "")

    async def fetch_repo(self, repo_url: str) -> dict:
        """Fetch repo info from GitHub API."""
        try:
            # Extract owner/repo from URL
            import re
            match = re.search(r"github\.com/([^/]+)/([^/\s]+)", repo_url)
            if not match:
                return {"error": "Invalid GitHub URL"}

            owner, repo = match.group(1), match.group(2).rstrip("/")
            headers = {"Authorization": f"token {self.token}"} if self.token else {}

            async with aiohttp.ClientSession() as session:
                # Get repo info
                async with session.get(
                    f"https://api.github.com/repos/{owner}/{repo}",
                    headers=headers
                ) as resp:
                    repo_data = await resp.json()

                # Get recent commits
                async with session.get(
                    f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=5",
                    headers=headers
                ) as resp:
                    commits = await resp.json()

                # Get languages
                async with session.get(
                    f"https://api.github.com/repos/{owner}/{repo}/languages",
                    headers=headers
                ) as resp:
                    languages = await resp.json()

            return {
                "name": repo_data.get("name", ""),
                "description": repo_data.get("description", ""),
                "stars": repo_data.get("stargazers_count", 0),
                "forks": repo_data.get("forks_count", 0),
                "language": repo_data.get("language", ""),
                "languages": list(languages.keys()) if isinstance(languages, dict) else [],
                "commits": [
                    c.get("commit", {}).get("message", "")[:100]
                    for c in (commits if isinstance(commits, list) else [])
                ],
                "url": repo_url
            }
        except Exception as e:
            return {"error": str(e)}

    async def run(self, task: str, context: dict) -> dict:
        try:
            api_key  = context.get("api_key", "")
            provider = context.get("provider", "gemini")
            model    = context.get("model", "gemini-2.0-flash")
            repo_url = context.get("repo_url", "")

            repo_info = ""
            if repo_url:
                data = await self.fetch_repo(repo_url)
                if "error" not in data:
                    repo_info = f"""
Repository: {data['name']}
Description: {data['description']}
Stars: {data['stars']} | Forks: {data['forks']}
Languages: {', '.join(data['languages'])}
Recent commits: {chr(10).join(data['commits'][:3])}
"""

            system = "[GITHUB AGENT] You are an expert software engineer and code reviewer. Analyze repositories thoroughly, suggest improvements, identify issues, and generate professional README files."
            messages = [{"role": "user", "content": task + ("\n\n" + repo_info if repo_info else "")}]
            full = ""
            async for chunk in generate_response(messages, provider, model, api_key, system):
                full += chunk

            return self.success(full, data={"repo_url": repo_url})
        except Exception as e:
            return self.failure(f"GitHub agent failed: {str(e)}")
