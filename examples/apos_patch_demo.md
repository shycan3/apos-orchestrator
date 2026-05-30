# APOS apos-patch approval demo

This example is the browser-bridge path.

1. Start the local WebSocket server:

```bash
python server/apos_server.py
```

2. Paste the following pair into ChatGPT or Gemini.

```apos-patch
{
  "patch_id": "demo-apos-patch",
  "project_root": "C:/Users/DO/Documents/apos-orchestrator",
  "target": "workspace/approved_demo.py",
  "language": "python",
  "sha256": "..."
}
```

```python
def main():
    print("approved demo from APOS")


if __name__ == "__main__":
    main()
```

3. After the server returns `validation_passed`, approve the patch with:

```javascript
window.__APOS_V32__.commit("demo-apos-patch")
```

The server writes `workspace/approved_demo.py` only after `commit_patch`.