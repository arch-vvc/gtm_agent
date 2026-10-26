from google import genai

client=genai.Client()

response=client.models.generate_content(
    model="gemini-3.5-lite",
    contents="in one sentence, what does a gtm engineer do?"
)

print(response.text)