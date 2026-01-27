import streamlit as st
import numpy as np
import pandas as pd
import sqlite3
import itertools
import uuid
import os

# ===============================
# AHP – Consistency Ratio
# ===============================
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

# ===============================
# DATABASE
# ===============================
DB = "data/database.db"

def get_db():
    return sqlite3.connect(DB)

def init_db():
    os.makedirs("data", exist_ok=True)
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

# ===============================
# STREAMLIT UI
# ===============================
st.set_page_config(page_title="AHP Survey", layout="wide")

st.title("Encuesta AHP – Proceso Analítico Jerárquico")

menu = st.sidebar.radio(
    "Menú",
    ["Crear proyecto (Admin)", "Responder encuesta"]
)

# =====================================================
# ADMIN – CREATE PROJECT
# =====================================================
if menu == "Crear proyecto (Admin)":

    st.header("Crear nuevo proyecto AHP")

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
        if project_name and all(criteria):
            project_id = str(uuid.uuid4())

            with get_db() as con:
                cur = con.cursor()
                cur.execute(
                    "INSERT INTO projects VALUES (?,?)",
                    (project_id, project_name)
                )
                for c in criteria:
                    cur.execute(
                        "INSERT INTO criteria VALUES (?,?)",
                        (project_id, c)
                    )
                con.commit()

            st.success("Proyecto creado")
            st.code(f"Link para encuestados:\n\nhttps://TU-APP.streamlit.app/?project_id={project_id}")

        else:
            st.error("Complete todos los campos")

# =====================================================
# SURVEY – RESPONDENT
# =====================================================
if menu == "Responder encuesta":

    project_id = st.query_params.get("project_id", None)

    if not project_id:
        st.warning("Acceda mediante el enlace del proyecto")
        st.stop()

    with get_db() as con:
        cur = con.cursor()
        cur.execute(
            "SELECT name FROM criteria WHERE project_id=?",
            (project_id,)
        )
        criteria = [c[0] for c in cur.fetchall()]

    if not criteria:
        st.error("Proyecto no encontrado")
        st.stop()

    st.subheader("Introducción")
    st.write("""
    El Proceso Analítico Jerárquico (AHP) es un método multicriterio ampliamente utilizado para la toma de decisiones complejas, permitiendo comparar variables de forma estructurada y consistente, transformando juicios expertos en resultados cuantitativos confiables.
    
    El objetivo de esta encuesta es determinar el peso relativo de las variables que influyen en la aptitud del cultivo de café arábigo, considerando factores climatológicos, topográficos, edáficos y socioeconómicos.
    
    La evaluación se realiza mediante comparaciones por pares. En cada fila se presentan dos criterios y el experto debe:
    Seleccionar cuál criterio es más importante.
    Asignar una intensidad de preferencia de 1 a 9 según la escala de Saaty.
    En cada fila se presentan dos criterios. Usted debe:
    • Seleccionar cuál es más importante
    • Indicar la intensidad de preferencia según la escala AHP (1–9)
    
    Escala AHP:
    1 = Igual importancia · 3 = Moderada · 5 = Fuerte · 7 = Muy fuerte · 9 = Extrema (Los valores pares representan intensidades intermedias)
    """)

    user_name = st.text_input("Ingrese su nombre")

    pairs = list(itertools.combinations(range(len(criteria)), 2))
    matrix = np.ones((len(criteria), len(criteria)))

    st.subheader("Comparaciones por pares")

    for i, j in pairs:
        col1, col2, col3 = st.columns([3, 3, 4])

        with col1:
            choice = st.selectbox(
                f"{criteria[i]} vs {criteria[j]}",
                ["", criteria[i], criteria[j]],
                key=f"choice_{i}_{j}"
            )

        with col2:
            value = st.selectbox(
                "Intensidad",
                ["", 1, 2, 3, 4, 5, 6, 7, 8, 9],
                key=f"value_{i}_{j}"
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

        # ===============================
        # EXPORT EXCEL (BPMSG STYLE)
        # ===============================
        df_matrix = pd.DataFrame(
            matrix,
            index=criteria,
            columns=criteria
        )

        df_cr = pd.DataFrame({
            "Métrica": ["CR"],
            "Valor": [cr]
        })

        filename = f"data/Respuestas - {user_name}.xlsx"

        with pd.ExcelWriter(filename, engine="openpyxl") as writer:
            df_matrix.to_excel(writer, sheet_name="Matriz_AHP")
            df_cr.to_excel(writer, sheet_name="Consistencia", index=False)

        response_id = str(uuid.uuid4())

        with get_db() as con:
            cur = con.cursor()
            cur.execute(
                "INSERT INTO responses VALUES (?,?,?,?,?)",
                (response_id, project_id, user_name, cr, filename)
            )
            con.commit()

        st.success("Encuesta enviada correctamente, gracias por su contribución")
        st.metric("CR", cr)

        with open(filename, "rb") as f:
            st.download_button(
                "Descargar su matriz AHP",
                data=f,
                file_name=f"Respuestas - {user_name}.xlsx"
            )
