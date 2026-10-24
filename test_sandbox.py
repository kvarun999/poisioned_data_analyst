import requests

url = "http://localhost:8080/analyze"
files = {'file': ('sales.csv', 'id,amount\n1,100\n2,200', 'text/csv')}
data = {'prompt': 'Calculate total sales'}

response = requests.post(url, files=files, data=data)
print(response.json())