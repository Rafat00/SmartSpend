from app import create_app

app = create_app()

if __name__ == "__main__":
    # debug=True gives auto-reload and detailed errors. Turn it off in production.
    app.run(debug=True)
