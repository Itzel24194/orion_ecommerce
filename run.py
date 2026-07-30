from app import create_app

app = create_app()

if __name__ == "__main__":
    # Al poner debug=True, el navegador te dirá EXACTAMENTE qué línea falla
    app.run(debug=True)