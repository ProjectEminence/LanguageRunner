"""
Ruby on Rails test runner using bundle and rails test.
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import re


from .base_runner import BaseTestRunner


class RubyTestRunner(BaseTestRunner):
    """Ruby on Rails test runner."""
    
    def detect_language(self, repo_path: str) -> bool:
        """Check if this is a Ruby/Rails project."""
        gemfile = Path(repo_path) / "Gemfile"
        return gemfile.exists()
    
    def setup_environment(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup Ruby environment: run bundle install.
        
        Args:
            repo_path: Path to the repository root
            
        Returns:
            Dictionary with setup results
        """
        try:
            repo_path_obj = Path(repo_path)
            gemfile = repo_path_obj / "Gemfile"
            
            if not gemfile.exists():
                return {
                    "success": False,
                    "error": "Gemfile not found"
                }
            
            # Run bundle install
            result = subprocess.run(
                ["bundle", "install"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to run bundle install: {result.stderr}",
                    "output": result.stdout
                }
            
            return {
                "success": True,
                "output": "Environment setup completed successfully"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Setup timed out"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Setup failed: {str(e)}"
            }
    
    def run_tests(self, repo_path: str, test_files: List[str]) -> Dict[str, Any]:
        """
        Run Rails tests on the given test files.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            
        Returns:
            Dictionary with test results
        """
        try:
            # Convert relative paths to absolute paths
            absolute_test_files = [str(Path(repo_path) / test_file) for test_file in test_files]
            
            # Filter out non-existent files
            existing_test_files = [f for f in absolute_test_files if Path(f).exists()]
            
            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "errors": ["No test files found"]
                }
            
            # Run Rails tests
            # Rails test command: bundle exec rails test <test_files>
            cmd = [
                "bundle", "exec", "rails", "test",
                *existing_test_files
            ]
            
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minutes timeout
            )
            
            # Parse Rails test output
            test_results = []
            errors = []
            
            # Parse Rails test output format
            # Example: "test_name#test_method (0.123s) PASSED" or "FAILED"
            lines = result.stdout.split('\n')
            current_test = None
            
            for line in lines:
                # Match Rails test output: "test_name#test_method (time) PASSED/FAILED"
                match = re.match(r'^(.+?)#(.+?)\s+\([\d.]+s\)\s+(PASSED|FAILED)', line)
                if match:
                    test_file, test_method, status = match.groups()
                    # Extract test file path from test_name
                    test_file_path = None
                    for tf in existing_test_files:
                        if Path(tf).stem in test_file or test_file in tf:
                            test_file_path = str(Path(tf).relative_to(repo_path))
                            break
                    
                    test_results.append({
                        "test_file": test_file_path or test_file,
                        "test_name": f"{test_file}#{test_method}",
                        "status": "passed" if status == "PASSED" else "failed",
                        "error": None,
                        "output": ""
                    })
                    current_test = len(test_results) - 1
                elif current_test is not None and line.strip() and test_results[current_test]["status"] == "failed":
                    # Append error details to current test
                    if test_results[current_test]["error"]:
                        test_results[current_test]["error"] += "\n" + line
                    else:
                        test_results[current_test]["error"] = line
            
            # If no structured results, create summary from return code
            if not test_results:
                for test_file in existing_test_files:
                    rel_path = str(Path(test_file).relative_to(repo_path))
                    test_results.append({
                        "test_file": rel_path,
                        "test_name": rel_path,
                        "status": "passed" if result.returncode == 0 else "failed",
                        "error": result.stderr if result.returncode != 0 else None,
                        "output": result.stdout
                    })
            
            return {
                "success": result.returncode == 0,
                "test_results": test_results,
                "errors": errors if errors else ([] if result.returncode == 0 else [result.stderr])
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "errors": ["Test execution timed out"]
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "errors": [f"Failed to run tests: {str(e)}"]
            }
