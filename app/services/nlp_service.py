# app/services/nlp_service.py
# ================================================================
# MOTOR DE NLP PARA CHATBOT ORION
# Usa spaCy + scikit-learn para clasificación de intenciones
# ================================================================

import os
import json
import random
import joblib
import numpy as np
from flask import current_app
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# spaCy es opcional: si no está instalado, se degrada a solo TF-IDF
try:
    import spacy
    NLP_ES = spacy.load("es_core_news_sm")
    SPACY_DISPONIBLE = True
except (ImportError, OSError):
    NLP_ES = None
    SPACY_DISPONIBLE = False


class NLPService:
    """Servicio de NLP para el chatbot de ORION"""

    MODELO_PATH = "models/chatbot_nlp.pkl"
    INTENTS_PATH = "data/intents.json"

    _pipeline = None
    _intents = None
    _respuestas_por_tag = None

    # ============================================================
    # CARGA DE DATOS
    # ============================================================

    @classmethod
    def _ruta(cls, relativa):
        return os.path.join(current_app.root_path, relativa)

    @classmethod
    def cargar_intents(cls):
        """Carga el dataset de intenciones desde intents.json"""
        if cls._intents is not None:
            return cls._intents
        ruta = cls._ruta(cls.INTENTS_PATH)
        with open(ruta, "r", encoding="utf-8") as f:
            data = json.load(f)
        cls._intents = data["intents"]
        cls._respuestas_por_tag = {i["tag"]: i["responses"] for i in cls._intents}
        return cls._intents

    # ============================================================
    # PREPROCESAMIENTO CON SPACY
    # ============================================================

    @classmethod
    def preprocesar(cls, texto):
        """
        Limpia y normaliza el texto usando spaCy:
        - Lematiza (reduce palabras a su raíz)
        - Elimina stopwords y signos
        - Convierte a minúsculas
        """
        if not texto:
            return ""
        texto = texto.lower().strip()

        if not SPACY_DISPONIBLE or NLP_ES is None:
            # Fallback simple: solo minúsculas
            return texto

        doc = NLP_ES(texto)
        tokens = [
            token.lemma_.lower()
            for token in doc
            if not token.is_stop
            and not token.is_punct
            and not token.is_space
            and len(token.text) > 1
        ]
        return " ".join(tokens)

    # ============================================================
    # EXTRACCIÓN DE ENTIDADES (NER)
    # ============================================================

    @classmethod
    def extraer_entidades(cls, texto):
        """
        Detecta entidades como productos, pedidos, ciudades, fechas.
        Retorna un diccionario con las entidades encontradas.
        """
        entidades = {"productos": [], "pedidos": [], "ciudades": [], "fechas": []}
        if not texto:
            return entidades

        # Regex para número de pedido (ej. #12345, PED-12345, ORD-001)
        import re
        pedidos = re.findall(r"(?:#|ped-|ord-|pedido\s*)(\d{3,})", texto.lower())
        entidades["pedidos"] = pedidos

        if SPACY_DISPONIBLE and NLP_ES is not None:
            doc = NLP_ES(texto)
            for ent in doc.ents:
                if ent.label_ in ("LOC", "GPE"):
                    entidades["ciudades"].append(ent.text)
                elif ent.label_ == "DATE":
                    entidades["fechas"].append(ent.text)
                elif ent.label_ in ("PRODUCT", "MISC", "ORG"):
                    entidades["productos"].append(ent.text)

        return entidades

    # ============================================================
    # ENTRENAMIENTO DEL MODELO
    # ============================================================

    @classmethod
    def entrenar(cls, forzar=False):
        """
        Entrena un Pipeline de TF-IDF + Logistic Regression
        con los patrones del intents.json.
        Guarda el modelo en disco.
        """
        ruta_modelo = cls._ruta(cls.MODELO_PATH)

        if not forzar and os.path.exists(ruta_modelo):
            try:
                cls._pipeline = joblib.load(ruta_modelo)
                print("[NLP] Modelo cargado desde disco")
                return {"success": True, "message": "Modelo cargado", "accuracy": None}
            except Exception as e:
                print(f"[NLP] Error cargando modelo: {e}")

        intents = cls.cargar_intents()
        X_raw = []
        y = []
        for intent in intents:
            for patron in intent["patterns"]:
                X_raw.append(patron)
                y.append(intent["tag"])

        if len(X_raw) < 10:
            return {"success": False, "message": "Datos insuficientes para entrenar"}

        # Preprocesar
        X = [cls.preprocesar(t) for t in X_raw]

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        # Pipeline
        pipeline = Pipeline([
            ("tfidf", TfidfVectorizer(
                ngram_range=(1, 2),
                max_features=1000,
                sublinear_tf=True,
                min_df=1
            )),
            ("clf", LogisticRegression(
                max_iter=1000,
                C=5.0,
                class_weight="balanced",
                random_state=42
            ))
        ])

        pipeline.fit(X_train, y_train)

        # Métricas
        y_pred = pipeline.predict(X_test)
        accuracy = float(accuracy_score(y_test, y_pred))
        reporte = classification_report(y_test, y_pred, output_dict=True, zero_division=0)

        # Guardar
        os.makedirs(os.path.dirname(ruta_modelo), exist_ok=True)
        joblib.dump(pipeline, ruta_modelo)
        cls._pipeline = pipeline

        print(f"[NLP] Modelo entrenado. Accuracy: {accuracy:.3f}")
        return {
            "success": True,
            "message": "Modelo entrenado correctamente",
            "accuracy": accuracy,
            "reporte": reporte,
            "n_ejemplos": len(X_raw),
            "n_intents": len(intents)
        }

    @classmethod
    def _obtener_pipeline(cls):
        if cls._pipeline is None:
            ruta = cls._ruta(cls.MODELO_PATH)
            if os.path.exists(ruta):
                cls._pipeline = joblib.load(ruta)
            else:
                cls.entrenar()
        return cls._pipeline

    # ============================================================
    # CLASIFICACIÓN DE INTENCIÓN
    # ============================================================

    @classmethod
    def clasificar_intencion(cls, mensaje):
        """
        Devuelve (tag, confianza) usando el modelo NLP.
        """
        pipeline = cls._obtener_pipeline()
        if pipeline is None:
            return "default", 0.0

        texto_proc = cls.preprocesar(mensaje)
        if not texto_proc:
            return "default", 0.0

        try:
            proba = pipeline.predict_proba([texto_proc])[0]
            idx = int(np.argmax(proba))
            tag = pipeline.classes_[idx]
            confianza = float(proba[idx])
            return tag, confianza
        except Exception as e:
            print(f"[NLP] Error clasificando: {e}")
            return "default", 0.0

    # ============================================================
    # GENERACIÓN DE RESPUESTA
    # ============================================================

    @classmethod
    def generar_respuesta(cls, mensaje, nombre_usuario=""):
        """
        Genera una respuesta inteligente basada en NLP.
        Retorna dict con: respuesta, intencion, confianza, entidades
        """
        cls.cargar_intents()
        tag, confianza = cls.clasificar_intencion(mensaje)
        entidades = cls.extraer_entidades(mensaje)

        # Si la confianza es muy baja, usar fallback
        if confianza < 0.25:
            tag = "default"

        respuestas = cls._respuestas_por_tag.get(tag, [])
        if not respuestas:
            respuestas = [
                "Gracias por tu mensaje. Un asesor se pondrá en contacto contigo pronto. 📝",
                "Entendido. ¿Podrías darme más detalles para poder ayudarte mejor?",
                "Tu consulta es importante. Permíteme un momento para revisar la información."
            ]
        respuesta = random.choice(respuestas)

        # Personalizar con el nombre
        if nombre_usuario and nombre_usuario not in ("Anónimo", "Cliente", ""):
            if tag == "saludo":
                respuesta = respuesta.replace("¡Hola!", f"¡Hola {nombre_usuario}!")

        # Añadir contexto si detectamos un pedido
        if entidades["pedidos"] and tag in ("pedido_estado", "envio"):
            respuesta += f" Veo que mencionas el pedido #{entidades['pedidos'][0]}. Déjame revisarlo."

        # Si el usuario pide hablar con humano
        if tag == "contacto" or "humano" in mensaje.lower() or "asesor" in mensaje.lower():
            respuesta += " Un asesor humano estará contigo en breve. 👤"

        return {
            "respuesta": respuesta,
            "intencion": tag,
            "confianza": round(confianza, 3),
            "entidades": entidades,
            "es_frecuente": confianza > 0.6
        }

    # ============================================================
    # INFORMACIÓN DEL MODELO
    # ============================================================

    @classmethod
    def info_modelo(cls):
        ruta = cls._ruta(cls.MODELO_PATH)
        existe = os.path.exists(ruta)
        info = {
            "modelo_existe": existe,
            "spacy_disponible": SPACY_DISPONIBLE,
            "intents_cargados": len(cls._intents) if cls._intents else 0,
            "ruta": ruta
        }
        if existe:
            try:
                pipeline = joblib.load(ruta)
                info["clases"] = list(pipeline.classes_)
            except Exception:
                pass
        return info