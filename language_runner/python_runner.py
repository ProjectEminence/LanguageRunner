"""
Python test runner using pytest with coverage support via pytest-cov.
"""
import json
import subprocess
import sys
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .base_runner import BaseTestRunner


def _parse_junit_xml(junit_path: Path) -> List[Dict[str, Any]]:
    """Parse pytest JUnit XML into list of result dicts (test_file, test_name, status, error, output)."""
    results: List[Dict[str, Any]] = []
    if not junit_path.exists() or junit_path.stat().st_size == 0:
        return results
    try:
        tree = ET.parse(junit_path)
    except (ET.ParseError, OSError):
        return results
    root = tree.getroot()
    for testcase in root.iter("testcase"):
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        # Pytest uses dotted module path for classname; convert to file path for test_file
        test_file = classname.replace(".", "/") + ".py" if classname else ""
        test_name = f"{test_file}::{name}" if test_file else name
        # JUnit: failure, error, skipped elements; else passed
        failure = testcase.find("failure")
        err = testcase.find("error")
        skipped = testcase.find("skipped")
        if failure is not None:
            status = "failed"
            error = (failure.get("message") or "") + "\n" + (failure.text or "")
        elif err is not None:
            status = "failed"
            error = (err.get("message") or "") + "\n" + (err.text or "")
        elif skipped is not None:
            status = "failed"
            error = skipped.get("message") or (skipped.text or "")
        else:
            status = "passed"
            error = None
        out_el = testcase.find("system-out")
        err_el = testcase.find("system-err")
        output = ""
        if out_el is not None and out_el.text:
            output = out_el.text.strip()
        if err_el is not None and err_el.text:
            output = (output + "\n" + err_el.text.strip()).strip() if output else err_el.text.strip()
        results.append({
            "test_file": test_file,
            "test_name": test_name,
            "status": status,
            "error": error,
            "output": output or "",
        })
    return results


def _parse_coverage_json(coverage_path: Path) -> Optional[Dict[str, Any]]:
    """Parse pytest-cov JSON coverage report into standardized format."""
    if not coverage_path.exists() or coverage_path.stat().st_size == 0:
        return None
    try:
        with open(coverage_path, 'r') as f:
            data = json.load(f)
        
        # Extract coverage totals
        totals = data.get('totals', {})
        line_pct = totals.get('percent_covered', 0)
        lines_covered = totals.get('covered_lines', 0)
        lines_total = totals.get('num_statements', 0)
        
        # Per-file coverage
        files_covered = []
        for file_path, file_data in data.get('files', {}).items():
            file_totals = file_data.get('totals', {})
            files_covered.append({
                'file': file_path,
                'line_coverage': file_totals.get('percent_covered', 0),
                'lines_covered': file_totals.get('covered_lines', 0),
                'lines_total': file_totals.get('num_statements', 0),
            })
        
        return {
            'line_coverage': line_pct,
            'lines_covered': lines_covered,
            'lines_total': lines_total,
            'files_covered': len(files_covered),
            'coverage_by_file': files_covered,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }
    except (json.JSONDecodeError, OSError, KeyError):
        return None




class PythonTestRunner(BaseTestRunner):
    """Python test runner using pytest."""
    
    def _find_python_dep_files(self, repo_path: str) -> tuple[Path | None, Path | None, Path | None]:
        """Find requirements.txt, setup.py, pyproject.toml at repo root or in any subdirectory."""
        root = Path(repo_path)
        req = root / "requirements.txt" if (root / "requirements.txt").exists() else next(root.rglob("requirements.txt"), None)
        setup = root / "setup.py" if (root / "setup.py").exists() else next(root.rglob("setup.py"), None)
        pyproject = root / "pyproject.toml" if (root / "pyproject.toml").exists() else next(root.rglob("pyproject.toml"), None)
        return (req, setup, pyproject)

    def _find_requirements_files(self, repo_path: str) -> List[Path]:
        """All requirements.txt under repo (root first, then subdirs)."""
        root = Path(repo_path)
        root_req = root / "requirements.txt"
        if root_req.exists():
            return [root_req] + [p for p in root.rglob("requirements.txt") if p != root_req]
        return list(root.rglob("requirements.txt"))


    def detect_language(self, repo_path: str) -> bool:
        """Check if this is a Python project (root or any subdirectory)."""
        req, setup, pyproject = self._find_python_dep_files(repo_path)
        return req is not None or setup is not None or pyproject is not None
    
    def _venv_pip(self, repo_path: str) -> Path:
        """Return the pip executable path for .venv inside repo_path."""
        venv = Path(repo_path) / ".venv"
        if os.name == "nt":
            return venv / "Scripts" / "pip.exe"
        return venv / "bin" / "pip"

    def _venv_python(self, repo_path: str) -> Path:
        """Return the Python executable path for .venv inside repo_path."""
        venv = Path(repo_path) / ".venv"
        if os.name == "nt":
            return venv / "Scripts" / "python.exe"
        return venv / "bin" / "python"

    def setup_environment(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup Python environment: create .venv in repo_path, install requirements.txt and pytest into it.
        
        Args:
            repo_path: Path to the repository root
            
        Returns:
            Dictionary with setup results
        """
        try:
            repo_path_obj = Path(repo_path)
            venv_path = repo_path_obj / ".venv"

            # Create .venv if it doesn't exist
            if not venv_path.exists():
                result = subprocess.run(
                    [sys.executable, "-m", "venv", str(venv_path)],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Failed to create virtual environment: {result.stderr}",
                        "output": result.stdout,
                    }

            pip_exe = self._venv_pip(repo_path)
            if not pip_exe.exists():
                return {
                    "success": False,
                    "error": f"Virtual environment pip not found at {pip_exe}",
                    "output": "",
                }

            requirements_files = self._find_requirements_files(repo_path)

            # Install from each requirements.txt (root first, then subdirs) using venv pip
            for requirements_file in requirements_files:
                result = subprocess.run(
                    [str(pip_exe), "install", "-r", str(requirements_file)],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=600,  # 10 minutes timeout
                )
                if result.returncode != 0:
                    return {
                        "success": False,
                        "error": f"Failed to install requirements from {requirements_file}: {result.stderr}",
                        "output": result.stdout,
                    }

            # Ensure pytest is installed in the venv
            pytest_result = subprocess.run(
                [str(pip_exe), "install", "pytest"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )
            if pytest_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to install pytest: {pytest_result.stderr}",
                    "output": pytest_result.stdout,
                }

            # Ensure pytest-cov is installed for coverage support
            cov_result = subprocess.run(
                [str(pip_exe), "install", "pytest-cov"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes timeout
            )
            if cov_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to install pytest-cov: {cov_result.stderr}",
                    "output": cov_result.stdout,
                }

            return {
                "success": True,
                "output": "Environment setup completed successfully",
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
    
    def run_tests(
        self,
        repo_path: str,
        test_files: List[str],
        include_coverage: bool = False
    ) -> Dict[str, Any]:
        """
        Run pytest on the given test files using the repo's .venv Python.
        
        Only runs Python (.py) test files. Non-Python paths are ignored.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            include_coverage: Whether to collect and return coverage data (default: False)
        
        Returns:
            Dictionary with test results. If include_coverage=True, also includes coverage data.
        """
        try:
            repo = Path(repo_path)
            venv_python = self._venv_python(repo_path)
            if not venv_python.exists():
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No .venv found in repo; run setup_environment first."],
                }

            python_test_files = [f for f in test_files if f.lower().endswith(".py")]
            if not python_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": [
                        "No Python test files (.py) to run. "
                        "Received paths may be for another language (e.g. .ts)."
                    ],
                }
            existing_test_files = [f for f in python_test_files if (repo / f).exists()]
            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No test files found"],
                }

            # Ensure conftest.py exists so repo root is on path when subprocess runs
            conftest_path = repo / "conftest.py"
            if not conftest_path.exists():
                conftest_path.write_text(
                    "import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\n"
                )

            with tempfile.NamedTemporaryFile(
                suffix=".xml", delete=False, prefix="pytest_junit_"
            ) as f:
                junit_path = Path(f.name)
            
            # Also create temp file for coverage if needed
            coverage_json_path = None
            if include_coverage:
                with tempfile.NamedTemporaryFile(
                    suffix=".json", delete=False, prefix="pytest_cov_"
                ) as f:
                    coverage_json_path = Path(f.name)
            
            try:
                cmd = [
                    str(venv_python),
                    "-m",
                    "pytest",
                    *existing_test_files,
                    "-v",
                    f"--junitxml={junit_path}",
                ]
                
                # Add coverage flags if requested
                if include_coverage and coverage_json_path:
                    cmd.extend([
                        f"--cov={repo_path}",
                        f"--cov-report=json:{coverage_json_path}",
                        "--cov-report=term-missing",
                    ])
                
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                exit_code = result.returncode
                stdout = result.stdout or ""
                stderr = result.stderr or ""

                if junit_path.exists():
                    test_results = _parse_junit_xml(junit_path)
                else:
                    test_results = []

                # Parse coverage data if requested
                coverage = None
                if include_coverage and coverage_json_path and coverage_json_path.exists():
                    coverage = _parse_coverage_json(coverage_json_path)

                errors: List[str] = []
                if exit_code != 0 and not any(r["status"] == "failed" for r in test_results):
                    if stderr or stdout:
                        errors.append("\n---\n".join(p for p in (stderr.strip(), stdout.strip()) if p))
                    else:
                        errors.append(f"pytest exited with code {exit_code}; no individual test results captured.")

                return {
                    "success": exit_code == 0,
                    "test_results": test_results,
                    "coverage": coverage,
                    "errors": errors,
                }
            finally:
                junit_path.unlink(missing_ok=True)
                if coverage_json_path:
                    coverage_json_path.unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": ["Test execution timed out"],
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": [f"Failed to run tests: {str(e)}"],
            }

    def run_tests_with_coverage(
        self,
        repo_path: str,
        test_files: List[str],
        coverage_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Run pytest with coverage on the given test files using the repo's .venv Python.
        
        Only runs Python (.py) test files. Non-Python paths are ignored.
        
        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)
            coverage_options: Optional dict with keys:
                - source: source directory to measure coverage (default: repo_path)
                - report_format: 'json' or 'xml' (default: 'json')
        
        Returns:
            Dictionary with test results and coverage data
        """
        coverage_options = coverage_options or {}
        source_dir = coverage_options.get('source', repo_path)
        
        try:
            repo = Path(repo_path)
            venv_python = self._venv_python(repo_path)
            if not venv_python.exists():
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No .venv found in repo; run setup_environment first."],
                }

            python_test_files = [f for f in test_files if f.lower().endswith(".py")]
            if not python_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": [
                        "No Python test files (.py) to run. "
                        "Received paths may be for another language (e.g. .ts)."
                    ],
                }
            existing_test_files = [f for f in python_test_files if (repo / f).exists()]
            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "coverage": None,
                    "errors": ["No test files found"],
                }

            # Ensure conftest.py exists so repo root is on path when subprocess runs
            conftest_path = repo / "conftest.py"
            if not conftest_path.exists():
                conftest_path.write_text(
                    "import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\n"
                )

            with tempfile.NamedTemporaryFile(
                suffix=".xml", delete=False, prefix="pytest_junit_"
            ) as f:
                junit_path = Path(f.name)
            
            with tempfile.NamedTemporaryFile(
                suffix=".json", delete=False, prefix="pytest_cov_"
            ) as f:
                coverage_json_path = Path(f.name)
            
            try:
                cmd = [
                    str(venv_python),
                    "-m",
                    "pytest",
                    *existing_test_files,
                    "-v",
                    f"--junitxml={junit_path}",
                    f"--cov={source_dir}",
                    f"--cov-report=json:{coverage_json_path}",
                    "--cov-report=term-missing",
                ]
                result = subprocess.run(
                    cmd,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )
                exit_code = result.returncode
                stdout = result.stdout or ""
                stderr = result.stderr or ""

                if junit_path.exists():
                    test_results = _parse_junit_xml(junit_path)
                else:
                    test_results = []

                # Parse coverage data
                coverage = _parse_coverage_json(coverage_json_path)

                errors: List[str] = []
                if exit_code != 0 and not any(r["status"] == "failed" for r in test_results):
                    if stderr or stdout:
                        errors.append("\n---\n".join(p for p in (stderr.strip(), stdout.strip()) if p))
                    else:
                        errors.append(f"pytest exited with code {exit_code}; no individual test results captured.")

                return {
                    "success": exit_code == 0,
                    "test_results": test_results,
                    "coverage": coverage,
                    "errors": errors,
                }
            finally:
                junit_path.unlink(missing_ok=True)
                coverage_json_path.unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": ["Test execution timed out"],
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "coverage": None,
                "errors": [f"Failed to run tests with coverage: {str(e)}"],
            }
