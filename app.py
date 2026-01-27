import streamlit as st
import numpy as np
import pandas as pd
import sqlite3
import itertools
import uuid
import os

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(
    page_title="Encuesta AHP – Café Arábigo",
    layout="wide"
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "database.db")

os.makedirs(DATA_DIR, exist_ok=True)

# =====================================================
# AHP – CONSISTENCY RATIO
# =====================================================
RI = {
    1: 0.00, 2: 0.00, 3: 0.58, 4: 0.90, 5: 1.12,
    6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49
}

def calculate_cr(matrix):
    matrix = np.array(matrix)
    n = matrix.shape[0]
    eigvals, _ = np.linalg.eig(matrix)
    lambda_max = max(eigvals.real)
    CI = (lambda_max - n) / (n - 1)
    CR = CI / RI[n] if n in RI else 0
    return round(CR, 4)

# =====================================================
# DATABASE
# =====================================================
def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with get_db() as con:
        cur = con.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS criteria (
            project_id TEXT,
            name TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            user_name TEXT,
            cr REAL,
            file_path TEXT
        )
        """)

        con.commit()

init_db()

# =====================================================
# ROUTING LOGIC
# =====================================================
project_id = st.query_params.get("project_id", None)

# =====================================================
# ADMIN – CREATE PROJECT
# =====================================================
if project_id is None:

    st.title("Administrador – Crear Encuesta AHP")

    project_name = st.text_input("Nombre del proyecto")
    n_criteria = st.number_input(
        "Número de criterios",
        min_value=2,
        max_value=10,
        step=1
    )

    criteria = []
    for i in range(int(n_criteria)):
        criteria.append(
            st.text_input(f"Criterio {i+1}")
        )

    if st.button("Crear proyecto"):
        if not project_name or not all(criteria):
            st.error("Complete todos los campos")
            st.stop()

        pid = str(uuid.uuid4())

        with get_db() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO projects VALUES (?, ?)",
                (pid, project_name)
            )
            for c in criteria:
                cur.execute(
                    "INSERT INTO criteria VALUES (?, ?)",
                    (pid, c)
                )
            con.commit()

        st.success("Proyecto creado correctamente")

        APP_URL = "ahp-app-encuestacafearabigo.streamlit.app"
        st.code(f"{APP_URL}/?project_id={pid}")

        st.info("Este enlace es el que debe enviar a los encuestados.")

# =====================================================
# RESPONDENT – SURVEY
# =====================================================
else:

    with get_db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM criteria WHERE project_id=?",
            (project_id,)
        )
        criteria = [c[0] for c in cur.fetchall()]

    if not criteria:
        st.error("Proyecto no encontrado o enlace inválido")
        st.stop()

    st.title("Encuesta AHP – Café Arábigo")

    st.markdown("""
    **Instrucciones**
    El Proceso Analítico Jerárquico (AHP) es un método multicriterio ampliamente utilizado para la toma de decisiones complejas, 
    permitiendo comparar variables de forma estructurada y consistente, transformando juicios expertos en resultados cuantitativos confiables.
    
    El objetivo de esta encuesta es determinar el peso relativo de las variables que influyen en la aptitud del cultivo de café arábigo, 
    considerando factores climatológicos, topográficos, edáficos y socioeconómicos.
    
    La evaluación se realiza mediante comparaciones por pares, En cada fila se presentan dos criterios. Usted debe:
    1. Seleccionar cuál criterio es más importante
    2. Indicar la intensidad de preferencia (escala 1–9 de Saaty)
    
    **Escala AHP**  
    1 = Igual · 3 = Moderada · 5 = Fuerte · 7 = Muy fuerte · 9 = Extrema  
    (Los valores pares representan intensidades intermedias)
    """)

    user_name = st.text_input("Ingrese su nombre")

    pairs = list(itertools.combinations(range(len(criteria)), 2))
    matrix = np.ones((len(criteria), len(criteria)))

    st.subheader("Comparaciones por pares")

    for i, j in pairs:
        c1, c2, c3 = st.columns([4, 4, 3])

        with c1:
            choice = st.selectbox(
                f"{criteria[i]} vs {criteria[j]}",
                ["", criteria[i], criteria[j]],
                key=f"c_{i}_{j}"
            )

        with c2:
            value = st.selectbox(
                "Intensidad",
                ["", 1, 2, 3, 4, 5, 6, 7, 8, 9],
                key=f"v_{i}_{j}"
            )

        if choice and value:
            if choice == criteria[i]:
                matrix[i][j] = value
                matrix[j][i] = 1 / value
            else:
                matrix[j][i] = value
                matrix[i][j] = 1 / value

    if st.button("Enviar encuesta"):
        if not user_name:
            st.error("Ingrese su nombre")
            st.stop()

        cr = calculate_cr(matrix)

        df_matrix = pd.DataFrame(
            matrix,
            index=criteria,
            columns=criteria
        )

        df_cr = pd.DataFrame(
            {"Métrica": ["CR"], "Valor": [cr]}
        )

        file_name = f"{user_name}_{uuid.uuid4().hex[:6]}.xlsx"
        file_path = os.path.join(DATA_DIR, file_name)

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df_matrix.to_excel(writer, sheet_name="Matriz_AHP")
            df_cr.to_excel(writer, sheet_name="Consistencia", index=False)

        with get_db() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO responses VALUES (?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    project_id,
                    user_name,
                    cr,
                    file_path
                )
            )
            con.commit()

        st.success("Encuesta enviada correctamente, gracias por su contribución")
        st.metric("Consistency Ratio (CR)", cr)

        with open(file_path, "rb") as f:
            st.download_button(
                "Descargar matriz AHP",
                data=f,
                file_name=f"Matriz_AHP_{user_name}.xlsx"
            )
