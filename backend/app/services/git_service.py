import asyncio
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from backend.app.core.logging import get_logger

logger = get_logger("git_service")

class GitSafetyError(Exception):
    pass


@dataclass
class GitStatus:
    is_clean: bool
    current_sha: str
    modified_files: List[str] = field(default_factory=list)
    untracked_files: List[str] = field(default_factory=list)


class GitService:
    """
    Safely inspects Git state, tracks repository SHA, captures diffs,
    and enforces workspace safety boundaries so ShipProof never clobbers
    user modifications or files outside the target project directory.
    """

    @staticmethod
    def _run_git_cmd(args: List[str], cwd: Path) -> Tuple[int, str, str]:
        try:
            res = subprocess.run(
                ["git"] + args,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as e:
            logger.error(f"Failed to execute git command {args} in {cwd}: {e}")
            return -1, "", str(e)

    @classmethod
    def get_current_sha(cls, repo_dir: Path) -> str:
        code, out, err = cls._run_git_cmd(["rev-parse", "HEAD"], repo_dir)
        if code == 0 and out:
            return out
        # Fallback if no commits yet
        return "uncommitted_init"

    @classmethod
    def inspect_status(cls, repo_dir: Path) -> GitStatus:
        current_sha = cls.get_current_sha(repo_dir)
        code, out, err = cls._run_git_cmd(["status", "--porcelain"], repo_dir)
        
        modified = []
        untracked = []
        
        if code == 0 and out:
            for line in out.splitlines():
                if not line.strip():
                    continue
                status_code = line[:2].strip()
                file_path = line[3:].strip()
                if status_code in ("M", "MM", "AM", "D"):
                    modified.append(file_path)
                elif status_code in ("??", "A"):
                    untracked.append(file_path)

        is_clean = len(modified) == 0
        return GitStatus(
            is_clean=is_clean,
            current_sha=current_sha,
            modified_files=modified,
            untracked_files=untracked
        )

    @classmethod
    def capture_diff(cls, repo_dir: Path, target_subpath: Optional[Path] = None) -> str:
        args = ["diff", "HEAD"]
        if target_subpath and target_subpath != repo_dir:
            try:
                rel = target_subpath.relative_to(repo_dir)
                args.append(str(rel))
            except ValueError:
                pass

        code, out, err = cls._run_git_cmd(args, repo_dir)
        if code != 0 or not out:
            # Fallback to unstaged diff
            code, out, err = cls._run_git_cmd(["diff"], repo_dir)
        return out or ""

    @classmethod
    def get_modified_files(cls, repo_dir: Path) -> List[str]:
        code, out, err = cls._run_git_cmd(["diff", "--name-only"], repo_dir)
        files = []
        if code == 0 and out:
            files.extend([f.strip() for f in out.splitlines() if f.strip()])
            
        # Also include untracked new files
        code, out, err = cls._run_git_cmd(["ls-files", "--others", "--exclude-standard"], repo_dir)
        if code == 0 and out:
            files.extend([f.strip() for f in out.splitlines() if f.strip()])
            
        return sorted(list(set(files)))

    @classmethod
    def validate_modifications(cls, repo_dir: Path, allowed_subpath: Path) -> Tuple[bool, List[str]]:
        """
        Validates that all modified and untracked files are strictly within allowed_subpath.
        Rejects modifications outside the approved project boundary.
        """
        modified_files = cls.get_modified_files(repo_dir)
        allowed_rel = str(allowed_subpath.resolve().relative_to(repo_dir.resolve()))
        
        violations = []
        for f in modified_files:
            file_abs = (repo_dir / f).resolve()
            if not str(file_abs).startswith(str(allowed_subpath.resolve())):
                violations.append(f)

        is_valid = len(violations) == 0
        return is_valid, violations

    @classmethod
    def rollback_files(cls, repo_dir: Path, files: List[str]) -> bool:
        """
        Selectively rolls back only the specified modified files without touching
        unrelated user work.
        """
        if not files:
            return True
        logger.info(f"Selectively rolling back files: {files}")
        code, _, err = cls._run_git_cmd(["checkout", "--"] + files, repo_dir)
        return code == 0
