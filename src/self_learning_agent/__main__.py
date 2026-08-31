import uvicorn

if __name__ == "__main__":
    uvicorn.run("self_learning_agent.api:app", host="0.0.0.0", port=8000, reload=False)
