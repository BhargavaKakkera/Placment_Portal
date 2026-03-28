import ast
from pathlib import Path
import unittest


UI_FILES = [
    Path("app/ui/public.py"),
    Path("app/ui/student.py"),
    Path("app/ui/company.py"),
    Path("app/ui/admin.py"),
]


def _is_router_post(decorator: ast.expr) -> bool:
    return (
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and isinstance(decorator.func.value, ast.Name)
        and decorator.func.value.id == "router"
        and decorator.func.attr == "post"
    )


class UiCsrfContractTests(unittest.TestCase):
    def test_all_ui_post_handlers_call_csrf_guard(self):
        missing = []
        for file_path in UI_FILES:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in tree.body:
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not any(_is_router_post(dec) for dec in node.decorator_list):
                    continue
                fn_source = ast.get_source_segment(source, node) or ""
                if "read_form_with_csrf(" not in fn_source:
                    missing.append(f"{file_path}:{node.name}")
        self.assertEqual(missing, [], f"Missing CSRF guard: {missing}")


if __name__ == "__main__":
    unittest.main()

