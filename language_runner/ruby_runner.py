"""
Ruby on Rails test runner using bundle and rails test with SimpleCov coverage support.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
import re
from datetime import datetime


from .base_runner import BaseTestRunner


class RubyTestRunner(BaseTestRunner):
    """Ruby on Rails test runner."""
    
    def detect_language(self, repo_path: str) -> bool:
        """Check if this is a Ruby/Rails project."""
        gemfile = Path(repo_path) / "Gemfile"
        return gemfile.exists()
    
    def setup_environment(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup Ruby environment: run bundle install and ensure .codevalid/tests/test_helper.rb exists.

        Args:
            repo_path: Path to the repository root

        Returns:
            Dictionary with setup results (optionally files_to_commit)
        """
        try:
            repo_path_obj = Path(repo_path)
            gemfile = repo_path_obj / "Gemfile"

            if not gemfile.exists():
                return {
                    "success": False,
                    "error": "Gemfile not found",
                    "output": "",
                }

            # Run bundle install
            result = subprocess.run(
                ["bundle", "install"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to run bundle install: {result.stderr}",
                    "output": result.stdout,
                }

            # Ensure .codevalid/tests and test_helper.rb exist (for running tests under .codevalid)
            repo_root = Path(repo_path)
            codevalid_tests_dir = repo_root / ".codevalid" / "tests"
            codevalid_tests_dir.mkdir(parents=True, exist_ok=True)
            files_to_commit: List[str] = []

            test_helper_path = codevalid_tests_dir / "test_helper.rb"
            if not test_helper_path.exists():
                sample_path = Path(__file__).parent / "utils" / "test_helper.codevalid.rb"
                if sample_path.exists():
                    config_content = sample_path.read_text()
                    test_helper_path.write_text(config_content)
                    files_to_commit.append(".codevalid/tests/test_helper.rb")
                else:
                    raise Exception("Ruby test_helper config sample not found")

            # Add SimpleCov to Gemfile if not present (for coverage support)
            gemfile_path = repo_root / "Gemfile"
            if gemfile_path.exists():
                gemfile_content = gemfile_path.read_text()
                if 'simplecov' not in gemfile_content:
                    # Append SimpleCov and simplecov-json to Gemfile
                    with open(gemfile_path, 'a') as f:
                        f.write("\n# CodeValid coverage dependencies\n")
                        f.write("gem 'simplecov', group: :test\n")
                        f.write("gem 'simplecov-json', group: test\n")
                    files_to_commit.append("Gemfile")
                    
                    # Run bundle install again to install SimpleCov
                    bundle_result = subprocess.run(
                        ["bundle", "install"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        timeout=300,
                    )
                    if bundle_result.returncode != 0:
                        return {
                            "success": False,
                            "error": f"Failed to install SimpleCov: {bundle_result.stderr}",
                            "output": bundle_result.stdout,
                        }

            result_payload: Dict[str, Any] = {
                "success": True,
                "output": "Environment setup completed successfully",
            }
            if files_to_commit:
                result_payload["files_to_commit"] = files_to_commit
            return result_payload

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Setup timed out",
                "output": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Setup failed: {str(e)}",
                "output": "",
            }
    
    def run_tests(
        self,
        repo_path: str,
        test_files: List[str],
        include_coverage: bool = False
    ) -> Dict[str, Any]:
        """
        Run Rails tests on the given test files.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            include_coverage: Whether to collect and return coverage data (default: False)
        
        Returns:
            Dictionary with test results. If include_coverage=True, also includes coverage data.
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
                    "coverage": None,
                    "errors": ["No test files found"]
                }
            
            # Run Rails tests
            cmd = [
                "env",
                "RAILS_ENV=test",
                "RUBYLIB=.codevalid/tests",
                "bundle", "exec", "rails", "test",
                *existing_test_files,
            ]

            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes timeout
            )
            
            # Parse Rails test output
            test_results = []
            coverage = None
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
            
            # Try to parse SimpleCov coverage data if requested
            if include_coverage:
                coverage_file = repo_root / "coverage" / "coverage.json"
                if coverage_file.exists():
                    try:
                        with open(coverage_file, 'r') as f:
                            cov_data = json.load(f)
                        
                        total = cov_data.get('total', {})
                        covered_lines = total.get('covered_lines', 0)
                        total_lines = total.get('lines_of_code', 0)
                        line_coverage = (covered_lines / total_lines * 100) if total_lines > 0 else 0
                        
                        files_covered = []
                        for file_path, file_data in cov_data.get('files', {}).items():
                            file_metrics = file_data.get('metrics', {})
                            file_covered = file_metrics.get('covered_lines', 0)
                            file_total = file_metrics.get('lines_of_code', 0)
                            file_pct = (file_covered / file_total * 100) if file_total > 0 else 0
                            files_covered.append({
                                'file': file_path,
                                'line_coverage': round(file_pct, 2),
                                'lines_covered': file_covered,
                                'lines_total': file_total,
                            })
                        
                        coverage = {
                            'line_coverage': round(line_coverage, 2),
                            'lines_covered': covered_lines,
                            'lines_total': total_lines,
                            'files_covered': len(files_covered),
                            'coverage_by_file': files_covered,
                            'generated_at': datetime.utcnow().isoformat() + 'Z',
                        }
                    except (json.JSONDecodeError, KeyError, ZeroDivisionError, OSError):
                        pass  # Coverage parsing failed, leave coverage as None
            
            return {
                "success": result.returncode == 0,
                "test_results": test_results,
                "coverage": coverage,
                "errors": errors if errors else ([] if result.returncode == 0 else [result.stderr])
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": ["Test execution timed out"]
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": [f"Failed to run tests: {str(e)}"]
            }

    def run_tests_with_coverage(
        self,
        repo_path: str,
        test_files: List[str],
        coverage_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run Rails tests with SimpleCov coverage on the given test files.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            coverage_options: Optional dict (currently unused, for future options)
        
        Returns:
            Dictionary with test results and coverage data
        """
        coverage_options = coverage_options or {}
        
        try:
            # Convert relative paths to absolute paths
            absolute_test_files = [str(Path(repo_path) / test_file) for test_file in test_files]
            
            # Filter out non-existent files
            existing_test_files = [f for f in absolute_test_files if Path(f).exists()]
            
            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No test files found"]
                }
            
            # Create a SimpleCov config file
            repo_root = Path(repo_path)
            
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, prefix="simplecov_"
            ) as tmp:
                coverage_json_path = Path(tmp.name)
            
            # SimpleCov requires a formatter - we'll create a minimal JSON formatter
            simplecov_config = repo_root / "simplecov_config.rb"
            simplecov_config.write_text('''
require 'simplecov'
SimpleCov.start 'rails' do
  add_filter '/test/'
  add_filter '/config/'
  formatter SimpleCov::Formatter::JSONFormatter
end
''')
            
            # Run Rails tests with SimpleCov
            cmd = [
                "env",
                "RAILS_ENV=test",
                "RUBYLIB=.codevalid/tests",
                "bundle", "exec", "rails", "test",
                *existing_test_files,
            ]

            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 minutes timeout
            )
            
            # Parse Rails test output
            test_results = []
            errors = []
            
            # Parse Rails test output format
            lines = result.stdout.split('\n')
            
            for line in lines:
                match = re.match(r'^(.+?)#(.+?)\s+\([\d.]+s\)\s+(PASSED|FAILED)', line)
                if match:
                    test_file, test_method, status = match.groups()
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
            
            # Try to parse SimpleCov coverage data
            coverage = None
            coverage_file = repo_root / "coverage" / "coverage.json"
            if coverage_file.exists():
                try:
                    with open(coverage_file, 'r') as f:
                        cov_data = json.load(f)
                    
                    # Extract coverage metrics
                    total = cov_data.get('total', {})
                    covered_lines = total.get('covered_lines', 0)
                    total_lines = total.get('lines_of_code', 0)
                    line_coverage = (covered_lines / total_lines * 100) if total_lines > 0 else 0
                    
                    # Per-file coverage
                    files_covered = []
                    for file_path, file_data in cov_data.get('files', {}).items():
                        file_metrics = file_data.get('metrics', {})
                        file_covered = file_metrics.get('covered_lines', 0)
                        file_total = file_metrics.get('lines_of_code', 0)
                        file_pct = (file_covered / file_total * 100) if file_total > 0 else 0
                        files_covered.append({
                            'file': file_path,
                            'line_coverage': round(file_pct, 2),
                            'lines_covered': file_covered,
                            'lines_total': file_total,
                        })
                    
                    coverage = {
                        'line_coverage': round(line_coverage, 2),
                        'lines_covered': covered_lines,
                        'lines_total': total_lines,
                        'files_covered': len(files_covered),
                        'coverage_by_file': files_covered,
                        'generated_at': datetime.utcnow().isoformat() + 'Z',
                    }
                except (json.JSONDecodeError, KeyError, ZeroDivisionError) as e:
                    errors.append(f"Failed to parse coverage data: {e}")
            
            # Cleanup temp files
            simplecov_config.unlink(missing_ok=True)
            coverage_json_path.unlink(missing_ok=True)
            
            return {
                "success": result.returncode == 0,
                "test_results": test_results,
                "coverage": coverage,
                "errors": errors if errors else ([] if result.returncode == 0 else [result.stderr])
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": ["Test execution timed out"]
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": [f"Failed to run tests with coverage: {str(e)}"]
            }
