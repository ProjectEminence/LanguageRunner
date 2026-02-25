"""
TypeScript/JavaScript test runner using Jest.
"""
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Any, List

from .base_runner import BaseTestRunner


# Extensions that Jest typically runs (test files)
JEST_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx")


class TypeScriptTestRunner(BaseTestRunner):
    """TypeScript/JavaScript test runner using Jest."""

    def _find_package_json(self, repo_path: str) -> Path | None:
        """Find package.json at repo root or in any subdirectory."""
        root = Path(repo_path)
        if (root / "package.json").exists():
            return root / "package.json"
        return next(root.rglob("package.json"), None)

    def detect_language(self, repo_path: str) -> bool:
        """Check if this is a Node/TypeScript project (has package.json)."""
        return self._find_package_json(repo_path) is not None

    def setup_environment(self, repo_path: str) -> Dict[str, Any]:
        """
        Setup Node environment: npm install from package.json.

        Args:
            repo_path: Path to the repository root

        Returns:
            Dictionary with setup results
        """
        try:
            package_json = self._find_package_json(repo_path)
            if not package_json:
                return {
                    "success": False,
                    "error": "No package.json found",
                    "output": "",
                }

            install_dir = str(package_json.parent)
            result = subprocess.run(
                ["npm", "install"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes
            )

            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to run npm install: {result.stderr}",
                    "output": result.stdout,
                }
            # Ensure Jest is available (may be in devDependencies from package.json)
            jest_check = subprocess.run(
                ["npx", "jest", "--version"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if jest_check.returncode != 0:
                return {
                    "success": False,
                    "error": (
                        "Jest not found. Add jest to devDependencies in package.json, "
                        f"or install with: npm install -D jest. {jest_check.stderr}"
                    ),
                    "output": jest_check.stdout,
                }
            # run npm install --save-dev ts-jest @types/jest
            ts_jest_result = subprocess.run(
                ["npm", "install", "--save-dev", "ts-jest", "@types/jest"],
                cwd=install_dir,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if ts_jest_result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Failed to install ts-jest: {ts_jest_result.stderr}",
                    "output": ts_jest_result.stdout,
                }
            return {
                "success": True,
                "output": "Environment setup completed successfully",
            }

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

    def run_tests(self, repo_path: str, test_files: List[str]) -> Dict[str, Any]:
        """
        Run Jest on the given test files.

        Only runs TypeScript/JavaScript test files (.ts, .tsx, .js, .jsx).
        Non-matching paths are ignored.

        Args:
            repo_path: Path to the repository root
            test_files: List of test file paths (relative to repo_path)

        Returns:
            Dictionary with test results (same structure as Python runner)
        """
        try:
            ts_test_files = [
                f
                for f in test_files
                if f.lower().endswith(JEST_EXTENSIONS)
            ]
            if not ts_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "errors": [
                        "No TypeScript/JavaScript test files (.ts, .tsx, .js, .jsx) to run. "
                        "Received paths may be for another language (e.g. .py)."
                    ],
                }

            repo = Path(repo_path)
            absolute_test_files = [str(repo / f) for f in ts_test_files]
            existing_test_files = [f for f in absolute_test_files if Path(f).exists()]

            if not existing_test_files:
                return {
                    "success": False,
                    "test_results": [],
                    "errors": ["No test files found"],
                }

            package_json = self._find_package_json(repo_path)
            cwd = str(package_json.parent) if package_json else repo_path

            # Run Jest with JSON output to a temp file for reliable parsing
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            ) as tmp:
                output_file = tmp.name

            try:
                cmd = [
                    "npx",
                    "jest",
                    "--json",
                    f"--outputFile={output_file}",
                    "--no-cache",
                    # "--passWithNoTests",
                    "--runTestsByPath",
                    *existing_test_files,
                    "--preset=ts-jest",
                    "--testMatch '**/*.ts'",
                ]

                result = subprocess.run(
                    cmd,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 minutes
                )

                test_results = []
                errors: List[str] = []

                # Parse Jest JSON output
                if Path(output_file).exists():
                    try:
                        with open(output_file, "r") as f:
                            jest_output = json.load(f)
                        test_results = self._parse_jest_results(
                            jest_output, repo_path, existing_test_files
                        )
                        if result.returncode != 0 and not any(
                            r["status"] == "failed" for r in test_results
                        ):
                            errors = [result.stderr] if result.stderr else []
                    except (json.JSONDecodeError, KeyError) as e:
                        errors.append(f"Failed to parse Jest output: {e}")

                # Fallback if no JSON or parsing failed
                if not test_results:
                    for test_file in existing_test_files:
                        rel_path = str(Path(test_file).relative_to(repo_path))
                        test_results.append({
                            "test_file": rel_path,
                            "test_name": rel_path,
                            "status": "passed" if result.returncode == 0 else "failed",
                            "error": result.stderr if result.returncode != 0 else None,
                            "output": result.stdout,
                        })

                return {
                    "success": result.returncode == 0,
                    "test_results": test_results,
                    "errors": errors
                    if errors
                    else ([] if result.returncode == 0 else [result.stderr or ""]),
                }
            finally:
                Path(output_file).unlink(missing_ok=True)

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_results": [],
                "errors": ["Test execution timed out"],
            }
        except Exception as e:
            return {
                "success": False,
                "test_results": [],
                "errors": [f"Failed to run tests: {str(e)}"],
            }

    def _parse_jest_results(
        self,
        jest_output: Dict[str, Any],
        repo_path: str,
        existing_test_files: List[str],
    ) -> List[Dict[str, Any]]:
        """Convert Jest JSON output to the same structure as Python runner."""
        test_results: List[Dict[str, Any]] = []
        repo = Path(repo_path)

        for file_result in jest_output.get("testResults", []):
            file_name = file_result.get("name", "")
            try:
                rel_file = str(Path(file_name).relative_to(repo))
            except ValueError:
                rel_file = file_name

            for assertion in file_result.get("assertionResults", []):
                title = assertion.get("title", "")
                full_name = assertion.get("fullName", title)
                status = assertion.get("status", "failed")
                failure_messages = assertion.get("failureMessages", [])
                error_text = "\n".join(failure_messages) if failure_messages else None

                test_results.append({
                    "test_file": rel_file,
                    "test_name": f"{rel_file}::{full_name}",
                    "status": "passed" if status == "passed" else "failed",
                    "error": error_text,
                    "output": "",
                })

        return test_results
