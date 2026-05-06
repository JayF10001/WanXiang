import requests

url = "http://127.0.0.1:5000/api/register"
payload = {
    "email": "test@example.com",
    "password": "secure123",
    "name": "Test User"
}

response = requests.post(url, json=payload)
print(f"状态码: {response.status_code}")
print(f"响应内容: {response.text}")