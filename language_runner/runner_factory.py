"""
Factory for creating language-specific test runners.
"""
from pathlib import Path
from typing import Optional

from .base_runner import BaseTestRunner
from .python_runner import PythonTestRunner
from .ruby_runner import RubyTestRunner
from .typescript_runner import TypeScriptTestRunner


class TestRunnerFactory:
    """Factory for creating appropriate test runner based on repository."""
    
    _runners = [
        PythonTestRunner(),
        RubyTestRunner(),
        TypeScriptTestRunner(),
    ]
    
    @classmethod
    def get_runner(cls, repo_path: str) -> Optional[BaseTestRunner]:
        """
        Get the appropriate test runner for the repository.
        
        Args:
            repo_path: Path to the repository root
            
        Returns:
            Test runner instance or None if no runner matches
        """
        for runner in cls._runners:
            if runner.detect_language(repo_path):
                return runner
        
        return None
