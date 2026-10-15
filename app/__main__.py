import uvicorn

from app.config import HOST, PORT, load_dotenv


def main() -> None:
    load_dotenv()
    uvicorn.run("app.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
