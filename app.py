import os
import random
import json
import sqlite3
from html import escape
from datetime import date, datetime
from zoneinfo import ZoneInfo
from typing import Any

import streamlit as st

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


st.set_page_config(
    page_title="Arena Cup",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)


ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
TIMEZONE = ZoneInfo("America/Sao_Paulo")
REGISTRATION_DEADLINE = datetime(2026, 11, 27, 12, 30, tzinfo=TIMEZONE)
DRAW_TIME = datetime(2026, 11, 27, 15, 30, tzinfo=TIMEZONE)
TOURNAMENT_DATE = date(2026, 11, 30)
TEAM_COUNT = 8
MIN_TEAM_SIZE = 7
MAX_TEAM_SIZE = 8
DATABASE_PATH = os.environ.get("ARENA_DATABASE_PATH", "arena_cup.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def database_connection() -> Any:
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError(
                "A dependência psycopg não está instalada. "
                "Adicione-a ao requirements.txt antes de usar DATABASE_URL."
            )
        return psycopg.connect(DATABASE_URL, row_factory=dict_row)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def execute_query(connection: Any, query: str, parameters: tuple[Any, ...] = ()) -> Any:
    if DATABASE_URL:
        query = query.replace("?", "%s")
    return connection.execute(query, parameters)


def initialize_database() -> None:
    with database_connection() as connection:
        execute_query(
            connection,
            """
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                gender TEXT NOT NULL,
                year TEXT NOT NULL
            )
            """
        )
        execute_query(
            connection,
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )


def load_shared_state() -> None:
    with database_connection() as connection:
        rows = execute_query(
            connection,
            "SELECT id, name, gender, year FROM participants ORDER BY id"
        ).fetchall()
        st.session_state.participants = [dict(row) for row in rows]
        for key in ("teams", "matches", "bets", "audit_log", "bracket_size"):
            row = execute_query(
                connection,
                "SELECT value FROM app_state WHERE key = ?", (key,)
            ).fetchone()
            if row:
                st.session_state[key] = json.loads(row["value"])
        st.session_state.next_participant_id = max(
            [participant["id"] for participant in st.session_state.participants],
            default=0,
        ) + 1
        st.session_state.next_team_id = max(
            [team["id"] for team in st.session_state.teams], default=0
        ) + 1
        st.session_state.next_match_id = max(
            [match["id"] for match in st.session_state.matches], default=0
        ) + 1
        st.session_state.next_bet_id = max(
            [bet["id"] for bet in st.session_state.bets], default=0
        ) + 1


def save_shared_state() -> None:
    with database_connection() as connection:
        for key in ("teams", "matches", "bets", "audit_log", "bracket_size"):
            execute_query(
                connection,
                """
                INSERT INTO app_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, json.dumps(st.session_state[key], ensure_ascii=False)),
            )


def save_participant(participant: dict[str, Any]) -> None:
    with database_connection() as connection:
        execute_query(
            connection,
            """
            INSERT INTO participants (id, name, gender, year)
            VALUES (?, ?, ?, ?)
            """,
            (
                participant["id"],
                participant["name"],
                participant["gender"],
                participant["year"],
            ),
        )


def remove_participant(participant_id: int) -> None:
    with database_connection() as connection:
        execute_query(
            connection,
            "DELETE FROM participants WHERE id = ?",
            (participant_id,),
        )


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "participants": [],
        "teams": [],
        "matches": [],
        "bets": [],
        "audit_log": [],
        "admin_authenticated": False,
        "entry_completed": False,
        "entry_profile": "",
        "entry_name": "",
        "entry_participant_id": None,
        "bracket_size": 0,
        "next_team_id": 1,
        "next_participant_id": 1,
        "next_match_id": 1,
        "next_bet_id": 1,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if not st.session_state.get("shared_state_loaded"):
        initialize_database()
        load_shared_state()
        st.session_state.shared_state_loaded = True


def add_audit(message: str) -> None:
    st.session_state.audit_log.insert(
        0,
        {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "ação": message,
        },
    )
    save_shared_state()


def current_time() -> datetime:
    return datetime.now(TIMEZONE)


def get_team(team_id: int) -> dict[str, Any] | None:
    return next(
        (team for team in st.session_state.teams if team["id"] == team_id),
        None,
    )


def team_label(team_id: int) -> str:
    if team_id is None:
        return "A definir"
    team = get_team(team_id)
    return team["name"] if team else "Equipe removida"


def bracket_size_for(team_count: int) -> int:
    size = 2
    while size < team_count:
        size *= 2
    return size


def registration_is_open() -> bool:
    return current_time() < REGISTRATION_DEADLINE


def draw_is_due() -> bool:
    return current_time() >= DRAW_TIME


def team_sizes_for(participant_count: int) -> list[int]:
    base_size, remainder = divmod(participant_count, TEAM_COUNT)
    return [base_size + (1 if index < remainder else 0) for index in range(TEAM_COUNT)]


def draw_teams() -> bool:
    participants = list(st.session_state.participants)
    if len(participants) < TEAM_COUNT * MIN_TEAM_SIZE:
        st.error(
            f"São necessários pelo menos {TEAM_COUNT * MIN_TEAM_SIZE} atletas "
            f"para formar {TEAM_COUNT} equipes de {MIN_TEAM_SIZE}."
        )
        return False
    if len(participants) > TEAM_COUNT * MAX_TEAM_SIZE:
        st.error(
            f"O limite é de {TEAM_COUNT * MAX_TEAM_SIZE} atletas "
            f"({MAX_TEAM_SIZE} por equipe)."
        )
        return False

    women = [participant for participant in participants if participant["gender"] == "Mulher"]
    men = [participant for participant in participants if participant["gender"] == "Homem"]
    if len(women) < TEAM_COUNT * 2:
        st.error(
            f"São necessárias pelo menos {TEAM_COUNT * 2} mulheres "
            "para garantir duas em cada equipe."
        )
        return False
    if len(men) < TEAM_COUNT * 2:
        st.error(
            f"São necessários pelo menos {TEAM_COUNT * 2} homens "
            "para manter a composição mínima prevista no regulamento."
        )
        return False

    random.shuffle(women)
    random.shuffle(men)
    sizes = team_sizes_for(len(participants))
    teams = [
        {
            "id": index + 1,
            "name": f"Equipe {index + 1}",
            "members": [],
            "captain": "",
        }
        for index in range(TEAM_COUNT)
    ]

    for index, team in enumerate(teams):
        team["members"].extend(women[index * 2 : index * 2 + 2])

    remaining = women[TEAM_COUNT * 2 :] + men
    random.shuffle(remaining)
    for team, size in zip(teams, sizes):
        vacancies = size - len(team["members"])
        team["members"].extend(remaining[:vacancies])
        del remaining[:vacancies]
        random.shuffle(team["members"])
        team["captain"] = random.choice(team["members"])["name"]
        team["members"] = [participant["name"] for participant in team["members"]]

    st.session_state.teams = teams
    st.session_state.next_team_id = TEAM_COUNT + 1
    add_audit(
        f"Sorteio automático realizado em {current_time().strftime('%d/%m/%Y às %H:%M')}: "
        f"{len(participants)} atletas distribuídos em {TEAM_COUNT} equipes."
    )
    return True


def maybe_draw_teams() -> None:
    if (
        draw_is_due()
        and not st.session_state.teams
        and st.session_state.participants
    ):
        if draw_teams():
            create_random_matches()


@st.fragment(run_every="30s")
def scheduled_draw_check() -> None:
    load_shared_state()
    had_teams = bool(st.session_state.teams)
    maybe_draw_teams()
    if not had_teams and st.session_state.teams:
        st.rerun()


def match_label(match_id: int) -> str:
    match = next(
        (item for item in st.session_state.matches if item["id"] == match_id),
        None,
    )
    if not match:
        return "Jogo removido"
    return f"{team_label(match['team_a'])} × {team_label(match['team_b'])}"


def create_random_matches() -> None:
    if len(st.session_state.teams) < 2:
        st.warning("Cadastre pelo menos duas equipes para sortear os confrontos.")
        return

    if st.session_state.matches:
        st.warning("Já existe um sorteio. Use o botão de refazer para substituir os confrontos.")
        return

    team_ids = [team["id"] for team in st.session_state.teams]
    st.session_state.bracket_size = bracket_size_for(len(team_ids))
    team_ids += [None] * (st.session_state.bracket_size - len(team_ids))
    random.shuffle(team_ids)
    for index in range(0, len(team_ids), 2):
        team_a = team_ids[index]
        team_b = team_ids[index + 1]
        bye_team = team_a if team_b is None else team_b if team_a is None else None
        st.session_state.matches.append(
            {
                "id": st.session_state.next_match_id,
                "team_a": team_a,
                "team_b": team_b,
                "status": "Bye" if bye_team is not None else "Agendado",
                "winner": bye_team,
                "score": "",
            }
        )
        st.session_state.next_match_id += 1

    bye_count = sum(match["status"] == "Bye" for match in st.session_state.matches)
    add_audit(
        f"Chaveamento com {len(st.session_state.teams)} equipes criado "
        f"({st.session_state.bracket_size} vagas, {bye_count} bye(s))."
    )


def reset_matches() -> None:
    st.session_state.matches = []
    st.session_state.bets = []
    st.session_state.bracket_size = 0
    add_audit("Sorteio e apostas da rodada foram reiniciados.")


def render_bracket() -> None:
    if not st.session_state.matches:
        return

    st.markdown('<div class="section-title">Chaveamento da competição</div>', unsafe_allow_html=True)
    st.caption(
        f"{len(st.session_state.teams)} equipes inscritas em uma chave de "
        f"{st.session_state.bracket_size} vagas."
    )
    round_matches = st.session_state.matches
    round_number = 1
    while round_matches:
        columns = st.columns(len(round_matches))
        with columns[0]:
            st.markdown(f"**Rodada {round_number}**")
        for index, match in enumerate(round_matches):
            with columns[index]:
                team_a = team_label(match["team_a"])
                team_b = team_label(match["team_b"])
                if match["status"] == "Bye":
                    st.info(f"{team_a if match['team_a'] else team_b}\n\n**Bye**")
                elif match["status"] == "Finalizado":
                    st.success(
                        f"{team_a} × {team_b}\n\n"
                        f"Vencedor: **{team_label(match['winner'])}**"
                    )
                else:
                    st.container(border=True).write(f"{team_a} × {team_b}")

        if len(round_matches) == 1:
            break
        round_matches = [
            {"team_a": None, "team_b": None, "status": "A definir", "winner": None}
            for _ in range((len(round_matches) + 1) // 2)
        ]
        round_number += 1


def points_for_user(user: str) -> int:
    spent = sum(bet["amount"] for bet in st.session_state.bets if bet["user"] == user)
    won = sum(bet["payout"] for bet in st.session_state.bets if bet["user"] == user)
    return 1000 - spent + won


def register_bet(user: str, match_id: int, team_id: int, amount: int) -> None:
    if amount <= 0:
        st.error("Informe uma quantidade de pontos maior que zero.")
        return
    if amount > points_for_user(user):
        st.error("Saldo insuficiente para essa aposta.")
        return
    if any(
        bet["user"] == user and bet["match_id"] == match_id
        for bet in st.session_state.bets
    ):
        st.error("Você já apostou neste confronto.")
        return

    st.session_state.bets.append(
        {
            "id": st.session_state.next_bet_id,
            "user": user,
            "match_id": match_id,
            "team_id": team_id,
            "amount": amount,
            "payout": 0,
            "status": "Pendente",
        }
    )
    st.session_state.next_bet_id += 1
    add_audit(f"Aposta registrada por {user}.")
    st.success("Aposta registrada.")


def settle_bets(match: dict[str, Any]) -> None:
    if not match["winner"]:
        return
    for bet in st.session_state.bets:
        if bet["match_id"] != match["id"] or bet["status"] != "Pendente":
            continue
        if bet["team_id"] == match["winner"]:
            bet["payout"] = bet["amount"] * 2
            bet["status"] = "Vencedora"
        else:
            bet["status"] = "Perdida"


def render_header() -> None:
    st.markdown(
        """
        <style>
        :root {
            --arena-blue: #092c4c;
            --arena-blue-light: #0f4c81;
            --arena-orange: #f28c28;
            --arena-cream: #332315;
            --arena-surface: #151f2f;
            --arena-surface-raised: #1c293b;
            --arena-border: #2d4056;
            --arena-text: #f4f7fb;
            --arena-muted: #b7c5d6;
        }
        .stApp {
            background: linear-gradient(180deg, #0b1220 0%, #101a2a 48%, #0b1220 100%);
            color: var(--arena-text);
        }
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewContainer"] > .main,
        [data-testid="stAppViewContainer"] .main .block-container {
            background: transparent !important;
        }
        [data-testid="stAppViewContainer"] .main .block-container {
            color: var(--arena-text) !important;
        }
        [data-testid="stSidebar"] {
            background: #0a1c30 !important;
        }
        [data-testid="stSidebar"] * {
            color: #ffffff !important;
        }
        [data-testid="stHeader"] {
            background: rgba(11, 18, 32, .9);
        }
        [data-testid="stMetricValue"],
        [data-testid="stMetricLabel"],
        [data-testid="stMarkdownContainer"],
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] h4,
        label,
        p,
        li {
            color: var(--arena-text) !important;
        }
        [data-testid="stCaptionContainer"] {
            color: var(--arena-muted) !important;
        }
        [data-testid="stMetricValue"] {
            color: #ffffff !important;
        }
        [data-testid="stMetricLabel"] {
            color: var(--arena-muted) !important;
        }
        input,
        textarea,
        [data-baseweb="select"] > div,
        [data-baseweb="input"] > div,
        [data-testid="stNumberInput"] > div {
            background-color: var(--arena-surface) !important;
            color: var(--arena-text) !important;
            border-color: var(--arena-border) !important;
        }
        input::placeholder,
        textarea::placeholder {
            color: var(--arena-muted) !important;
        }
        [data-baseweb="popover"],
        [data-baseweb="menu"],
        [role="listbox"],
        [role="option"] {
            background-color: var(--arena-surface-raised) !important;
            color: var(--arena-text) !important;
        }
        [role="option"]:hover,
        [role="option"][aria-selected="true"] {
            background-color: #29415d !important;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid var(--arena-border);
            border-radius: 10px;
            overflow: hidden;
        }
        [data-testid="stAlert"] {
            background-color: var(--arena-surface) !important;
            border-color: var(--arena-border) !important;
        }
        [data-testid="stAlert"] p {
            color: var(--arena-text) !important;
        }
        .arena-hero {
            background: linear-gradient(115deg, var(--arena-blue), var(--arena-blue-light));
            border-radius: 20px;
            color: white;
            padding: 1.5rem 1.8rem;
            margin: 0 0 1.25rem;
            box-shadow: 0 10px 24px rgba(9, 44, 76, .18);
        }
        .arena-hero h1 {
            margin: 0;
            font-size: clamp(2rem, 5vw, 3.2rem);
            letter-spacing: -.04em;
        }
        .arena-hero p {
            margin: .35rem 0 0;
            color: #dceeff;
            font-size: 1.05rem;
        }
        .section-title {
            border-left: 5px solid var(--arena-orange);
            color: var(--arena-text);
            font-size: 1.45rem;
            font-weight: 800;
            margin: 1.25rem 0 .75rem;
            padding-left: .75rem;
        }
        .team-card {
            background: var(--arena-surface);
            border: 1px solid var(--arena-border);
            border-top: 5px solid var(--arena-orange);
            border-radius: 14px;
            box-shadow: 0 6px 16px rgba(0, 0, 0, .24);
            min-height: 150px;
            padding: 1rem 1.1rem;
            margin-bottom: 1rem;
        }
        .team-card.highlight {
            border: 2px solid var(--arena-orange);
            border-top-width: 7px;
            background: var(--arena-cream);
        }
        .team-card h3 {
            color: var(--arena-text);
            margin: 0 0 .4rem;
        }
        .team-card .captain {
            color: #ffb05c;
            font-weight: 700;
            margin-bottom: .55rem;
        }
        .team-card .members {
            color: var(--arena-muted);
            font-size: .92rem;
            line-height: 1.5;
        }
        .match-card {
            background: var(--arena-surface);
            border: 1px solid var(--arena-border);
            border-left: 5px solid var(--arena-blue-light);
            border-radius: 12px;
            padding: .8rem 1rem;
            margin: .5rem 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="arena-hero">
            <h1>🏆 Arena Cup</h1>
            <p>Torneio de handebol misto • integração, respeito e espírito esportivo</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Inscrição individual, sorteio automático de equipes e confrontos.")
    st.warning(
        "Modo demonstração: as apostas usam pontos virtuais e não envolvem dinheiro real. "
        "Qualquer ajuste administrativo fica registrado no log."
    )


def render_regulation() -> None:
    st.markdown('<div class="section-title">Regulamento Arena Cup</div>', unsafe_allow_html=True)
    st.markdown(
        """
        ### 1. Participação
        - O torneio é destinado a estudantes do **1º e 2º ano de Educação Física**.
        - A inscrição é individual e deve ser feita com nome, gênero e ano do curso.
        - As inscrições ficam abertas até **27/11/2026 às 12:30**.

        ### 2. Sorteio das equipes
        - Serão formadas **8 equipes**, com **7 ou 8 atletas** cada.
        - Cada equipe terá no mínimo **2 mulheres e 2 homens**.
        - O sorteio das equipes e dos capitães ocorrerá automaticamente em
          **27/11/2026 às 15:30**.
        - Depois do sorteio, as inscrições e a composição das equipes ficam bloqueadas.

        ### 3. Partidas
        - A competição será disputada em chave eliminatória com quartas de final,
          semifinais, disputa de terceiro lugar e final.
        - Cada partida terá **10 minutos corridos**.
        - Em caso de empate, a decisão será por **tiros de 7 metros**.
        - O resultado oficial é lançado pela administração e fica registrado no log
          de auditoria.

        ### 4. Apostas demonstrativas
        - As apostas usam exclusivamente **pontos virtuais**; não há dinheiro real.
        - Cada apostador começa com **1.000 pontos virtuais**.
        - É permitida uma aposta por usuário em cada confronto enquanto ele estiver
          agendado.
        - Os resultados lançados pela administração liquidam automaticamente as apostas.

        ### 5. Integridade e convivência
        - A participação deve respeitar os colegas, a organização e o espírito esportivo.
        - Correções administrativas devem ser justificadas e ficam registradas no log.
        - A organização poderá impedir cadastros incorretos ou duplicados para preservar
          a organização do torneio.
        """,
        unsafe_allow_html=False,
    )


def render_entry_screen() -> bool:
    if st.session_state.entry_completed:
        return True

    st.title("🏆 Arena Cup")
    st.subheader("Acesso ao Arena Cup")
    st.write("Faça um cadastro básico para acompanhar sua equipe após o sorteio.")

    with st.form("entry_form"):
        profile = st.radio(
            "Selecione uma opção",
            ["Competidor", "Apostador", "Administrador"],
            horizontal=True,
        )
        name = st.text_input(
            "Nome completo",
            placeholder="Digite seu nome completo",
        )
        participant_gender = "Mulher"
        participant_year = "1º ano"
        if profile == "Competidor":
            participant_gender = st.selectbox(
                "Gênero para composição das equipes",
                ["Mulher", "Homem"],
            )
            participant_year = st.selectbox("Ano do curso", ["1º ano", "2º ano"])
        admin_password = ""
        if profile == "Administrador":
            admin_password = st.text_input(
                "Senha do administrador",
                type="password",
                placeholder="Digite a senha administrativa",
            )
        entered = st.form_submit_button("Entrar", type="primary", use_container_width=True)

    if entered:
        if not name.strip():
            st.error("Digite seu nome para continuar.")
        elif profile == "Competidor":
            existing = next(
                (
                    participant
                    for participant in st.session_state.participants
                    if participant["name"].casefold() == name.strip().casefold()
                ),
                None,
            )
            if existing:
                st.session_state.entry_participant_id = existing["id"]
            elif not registration_is_open():
                st.error("As inscrições foram encerradas em 27/11/2026 às 12:30.")
                return False
            elif len(st.session_state.participants) >= TEAM_COUNT * MAX_TEAM_SIZE:
                st.error("As inscrições atingiram o limite de 64 atletas.")
                return False
            else:
                participant = {
                    "id": st.session_state.next_participant_id,
                    "name": name.strip(),
                    "gender": participant_gender,
                    "year": participant_year,
                }
                st.session_state.participants.append(participant)
                save_participant(participant)
                st.session_state.entry_participant_id = participant["id"]
                st.session_state.next_participant_id += 1
                add_audit(f"Atleta {name.strip()} realizou cadastro individual.")
                st.success("Cadastro realizado com sucesso.")
        if profile == "Administrador" and not ADMIN_PASSWORD:
            st.error("O painel administrativo ainda não foi configurado.")
        elif profile == "Administrador" and admin_password != ADMIN_PASSWORD:
            st.error("Senha administrativa incorreta.")
        elif profile != "Competidor" or st.session_state.entry_participant_id:
            st.session_state.entry_profile = profile
            st.session_state.entry_name = name.strip()
            st.session_state.entry_completed = True
            if profile == "Apostador":
                st.session_state.current_bettor = name.strip()
            elif profile == "Administrador":
                st.session_state.admin_authenticated = True
            add_audit(f"{profile} {name.strip()} entrou no sistema.")
            st.rerun()

    return False


initialize_state()
scheduled_draw_check()
if not render_entry_screen():
    st.stop()

render_header()

with st.sidebar:
    st.header("Navegação")
    st.caption(f"{st.session_state.entry_profile}: {st.session_state.entry_name}")
    if st.button("Trocar participante", use_container_width=True):
        st.session_state.entry_completed = False
        st.session_state.entry_profile = ""
        st.session_state.entry_name = ""
        st.session_state.entry_participant_id = None
        st.session_state.admin_authenticated = False
        st.rerun()
    st.divider()
    if st.session_state.entry_profile == "Competidor":
        available_pages = ["Tela principal", "Regulamento"]
    elif st.session_state.entry_profile == "Administrador":
        available_pages = ["Painel administrativo", "Regulamento"]
    else:
        available_pages = ["Confrontos e apostas", "Regulamento"]
    page = st.radio(
        "Ir para",
        available_pages,
        label_visibility="collapsed",
    )
    st.divider()
    if st.session_state.entry_profile == "Administrador":
        st.metric("Atletas inscritos", len(st.session_state.participants))
    st.metric("Confrontos", len(st.session_state.matches))

if page == "Regulamento":
    render_regulation()
elif page in ("Tela principal", "Confrontos e apostas"):
    st.markdown('<div class="section-title">Painel do torneio</div>', unsafe_allow_html=True)
    metric_a, metric_b, metric_c = st.columns(3)
    with metric_a:
        st.metric("Equipes", len(st.session_state.teams) or "—", "8 previstas")
    with metric_b:
        st.metric("Atletas", len(st.session_state.participants) or "—")
    with metric_c:
        st.metric("Confrontos", len(st.session_state.matches) or "—")
    if registration_is_open():
        st.info(
            "Inscrições abertas até 27/11/2026 às 12:30. "
            "O sorteio automático ocorrerá às 15:30."
        )
    elif not draw_is_due():
        st.warning(
            "Inscrições encerradas. O sorteio automático ocorrerá em "
            "27/11/2026 às 15:30."
        )
    if st.session_state.teams:
        participant_team = next(
            (
                team
                for team in st.session_state.teams
                if st.session_state.entry_name in team["members"]
            ),
            None,
        )
        if participant_team:
            st.success(f"Você caiu na **{participant_team['name']}**.")
        st.markdown('<div class="section-title">Equipes sorteadas</div>', unsafe_allow_html=True)
        for row_start in range(0, len(st.session_state.teams), 2):
            team_columns = st.columns(2)
            for column, team in zip(team_columns, st.session_state.teams[row_start : row_start + 2]):
                is_my_team = bool(participant_team and team["id"] == participant_team["id"])
                members = ", ".join(escape(member) for member in team["members"])
                highlight = " highlight" if is_my_team else ""
                marker = " • SUA EQUIPE" if is_my_team else ""
                with column:
                    st.markdown(
                        f"""
                        <div class="team-card{highlight}">
                            <h3>{escape(team['name'])}{marker}</h3>
                            <div class="captain">⭐ Capitão: {escape(team['captain'])}</div>
                            <div class="members"><b>{len(team['members'])} atletas</b><br>{members}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
    else:
        st.info("As equipes e os confrontos aparecerão aqui após o sorteio automático.")

    st.markdown('<div class="section-title">Confrontos e apostas</div>', unsafe_allow_html=True)
    if not st.session_state.teams:
        st.info(
            f"As equipes serão sorteadas automaticamente em "
            "27/11/2026 às 15:30, após o encerramento das inscrições."
        )
    user = st.text_input(
        "Seu nome",
        value=st.session_state.entry_name if st.session_state.entry_profile == "Apostador" else "",
        placeholder="Digite seu nome para participar das apostas",
        key="current_bettor",
    ).strip()
    if user:
        st.success(f"Olá, {user}! Seu saldo inicial é de 1.000 pontos virtuais.")
    else:
        st.info("Digite seu nome acima para habilitar o registro das apostas.")

    if not st.session_state.matches:
        st.info("A chave de 8 equipes será liberada após o sorteio automático.")
    else:
        render_bracket()
        st.metric("Saldo de pontos virtuais", points_for_user(user) if user else 1000)

        for match in st.session_state.matches:
            team_a = team_label(match["team_a"])
            team_b = team_label(match["team_b"])
            with st.container(border=True):
                st.markdown(
                    f'<div class="match-card"><b>{escape(team_a)} &nbsp; × &nbsp; '
                    f'{escape(team_b)}</b></div>',
                    unsafe_allow_html=True,
                )
                if match["status"] == "Bye":
                    st.info(f"{team_label(match['winner'])} avançou automaticamente por bye.")
                    continue
                if match["status"] == "Finalizado":
                    st.success(f"Resultado: {team_label(match['winner'])} venceu ({match['score']}).")
                    continue
                with st.form(f"bet_{match['id']}"):
                    choice = st.radio("Apostar em", [match["team_a"], match["team_b"]], format_func=team_label)
                    amount = st.number_input("Pontos", min_value=1, max_value=1000, value=100, step=10)
                    bet_submitted = st.form_submit_button("Registrar aposta")
                if bet_submitted:
                    if not user.strip():
                        st.error("Informe sua identificação antes de apostar.")
                    else:
                        register_bet(user.strip(), match["id"], choice, int(amount))

        if st.session_state.bets:
            st.subheader("Minhas apostas")
            selected_user = st.text_input("Consultar apostas de", key="bet_history_user")
            rows = [
                {
                    "Confronto": f"{team_label(bet['team_id'])}",
                    "Pontos": bet["amount"],
                    "Status": bet["status"],
                    "Retorno": bet["payout"],
                }
                for bet in st.session_state.bets
                if selected_user and bet["user"].casefold() == selected_user.strip().casefold()
            ]
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            elif selected_user:
                st.info("Nenhuma aposta encontrada para esse usuário.")

else:
    st.header("Painel administrativo")
    if not st.session_state.admin_authenticated:
        st.write("Área restrita para lançar resultados e gerenciar a rodada.")
        with st.form("admin_login"):
            password = st.text_input("Senha administrativa", type="password")
            login = st.form_submit_button("Entrar")
        if login:
            if not ADMIN_PASSWORD:
                st.error("O painel administrativo ainda não foi configurado.")
            elif password == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.error("Senha inválida.")
    else:
        if st.button("Sair da área administrativa"):
            st.session_state.admin_authenticated = False
            st.rerun()

        st.subheader("Inscritos")
        if st.session_state.participants:
            st.dataframe(
                [
                    {
                        "Nome": participant["name"],
                        "Gênero": participant["gender"],
                        "Ano": participant["year"],
                    }
                    for participant in st.session_state.participants
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhum participante inscrito.")

        st.subheader("Gerenciar inscrições")
        if st.session_state.matches:
            st.warning(
                "O chaveamento já foi criado. As inscrições e equipes estão bloqueadas "
                "para preservar a integridade da competição."
            )
        elif st.session_state.teams:
            st.info("O sorteio das equipes já foi realizado; as inscrições estão bloqueadas.")
        else:
            st.caption(
                f"{len(st.session_state.participants)} atletas inscritos. "
                "Remova inscrições duplicadas ou incorretas antes da data do sorteio."
            )
            for participant in st.session_state.participants:
                participant_col, action_col = st.columns([5, 1])
                with participant_col:
                    st.write(
                        f"**{participant['name']}** — "
                        f"{participant['gender']}, {participant['year']}"
                    )
                with action_col:
                    if st.button("Excluir", key=f"delete_participant_{participant['id']}"):
                        st.session_state.participants = [
                            item
                            for item in st.session_state.participants
                            if item["id"] != participant["id"]
                        ]
                        remove_participant(participant["id"])
                        save_shared_state()
                        add_audit(f"Inscrição de {participant['name']} excluída pelo administrador.")
                        st.success(f"Inscrição de {participant['name']} excluída.")
                        st.rerun()

        st.subheader("Lançar resultados")
        for match in st.session_state.matches:
            if match["status"] == "Bye":
                st.info(f"{team_label(match['winner'])} avançou automaticamente por bye.")
                continue
            with st.form(f"result_{match['id']}"):
                winner = st.selectbox(
                    f"Vencedor — {team_label(match['team_a'])} × {team_label(match['team_b'])}",
                    [match["team_a"], match["team_b"]],
                    format_func=team_label,
                    index=0 if not match["winner"] else [match["team_a"], match["team_b"]].index(match["winner"]),
                )
                score = st.text_input("Placar", value=match["score"], placeholder="Ex.: 2 x 1")
                save_result = st.form_submit_button("Salvar resultado")
            if save_result:
                match["winner"] = winner
                match["score"] = score.strip() or "Placar não informado"
                match["status"] = "Finalizado"
                settle_bets(match)
                add_audit(
                    f"Resultado ajustado manualmente: {team_label(winner)} venceu "
                    f"{team_label(match['team_a'])} x {team_label(match['team_b'])}."
                )
                st.success("Resultado salvo e apostas liquidadas.")

        st.subheader("Apostas registradas")
        if st.session_state.bets:
            st.dataframe(
                [
                    {
                        "Apostador": bet["user"],
                        "Jogo": match_label(bet["match_id"]),
                        "Equipe escolhida": team_label(bet["team_id"]),
                        "Pontos": bet["amount"],
                        "Status": bet["status"],
                    }
                    for bet in st.session_state.bets
                ],
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma aposta registrada.")

        st.subheader("Log de auditoria")
        if st.session_state.audit_log:
            st.dataframe(st.session_state.audit_log, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma ação registrada.")
