import json
import urllib.error
import urllib.request

def make_job(token=None):
    boundary = "----WebKitBoundaryQuotaTest123"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="operation"\r\n\r\n'
        "html_to_pdf\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="options"\r\n\r\n'
        '{"url": "https://example.com"}\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request("http://127.0.0.1:8501/api/jobs", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())

if __name__ == "__main__":
    print("Testing Guest Free Quota...")
    for i in range(1, 8):
        status, data = make_job()
        if status == 202:
            print(f"Op {i}: HTTP {status} Queued successfully (Job ID: {data['job_id']})")
        else:
            print(f"Op {i}: HTTP {status} Detail: {data['detail']}")
