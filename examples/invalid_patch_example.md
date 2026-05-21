# Invalid APOS Patch Example

This example has valid metadata and a matching hash, but the Python source fails `py_compile` because the function definition has no colon.

```apos-patch
{
  "patch_id": "patch-invalid-python-001",
  "project_root": "C:/Users/DO/Desktop/test-project",
  "target": "workspace/active_code.py",
  "language": "python",
  "sha256": "b1a921baa26dc478c7e4380d579cddb0d6734afc19c4baeb81bc2224110ffd10"
}
```

```python
def main()
    print("missing colon")
```
