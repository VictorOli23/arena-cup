import os
import random
from datetime import datetime
from typing import Any

import streamlit as st


st.set_page_config(
    page_title="Arena Cup",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)


ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "teams": [],
        "matches": [],
        "bets": [],
        "audit_log": [],
        "admin_authenticated": False,
        "entry_completed": False,
        "entry_profile": "",
        "entry_name": "",
        "new_team_members": [""],
        "bracket_size": 0,
        "next_team_id": 1,
        "next_match_id": 1,
        "next_bet_id": 1,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_audit(message: str) -> None:
    st.session_state.audit_log.insert(
        0,
        {
            "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "ação": message,
        },
    )


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


def delete_team(team_id: int) -> None:
    team = get_team(team_id)
    if not team:
        return
    st.session_state.teams = [
        item for item in st.session_state.teams if item["id"] != team_id
    ]
    add_audit(f"Equipe {team['name']} excluída pelo administrador.")


def render_bracket() -> None:
    if not st.session_state.matches:
        return

    st.subheader("Chaveamento da competição")
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
    st.title("🏆 Arena Cup")
    st.caption("Inscrição de equipes, sorteio de confrontos e apostas com pontos fictícios.")
    st.warning(
        "Modo demonstração: as apostas usam pontos virtuais e não envolvem dinheiro real. "
        "Qualquer ajuste administrativo fica registrado no log."
    )


def render_entry_screen() -> bool:
    if st.session_state.entry_completed:
        return True

    st.title("🏆 Arena Cup")
    st.subheader("Como você vai participar?")
    st.write("Escolha seu perfil e informe seu nome para entrar no sistema.")

    with st.form("entry_form"):
        profile = st.radio(
            "Selecione uma opção",
            ["Competidor", "Apostador", "Administrador"],
            horizontal=True,
        )
        name = st.text_input(
            "Seu nome",
            placeholder="Digite seu nome",
        )
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
        elif profile == "Administrador" and not ADMIN_PASSWORD:
            st.error("O painel administrativo ainda não foi configurado.")
        elif profile == "Administrador" and admin_password != ADMIN_PASSWORD:
            st.error("Senha administrativa incorreta.")
        else:
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
        st.session_state.admin_authenticated = False
        st.rerun()
    st.divider()
    if st.session_state.entry_profile == "Competidor":
        available_pages = ["Inscrição", "Confrontos e apostas"]
    elif st.session_state.entry_profile == "Administrador":
        available_pages = ["Painel administrativo"]
    else:
        available_pages = ["Confrontos e apostas"]
    page = st.radio(
        "Ir para",
        available_pages,
        label_visibility="collapsed",
    )
    st.divider()
    st.metric("Equipes inscritas", len(st.session_state.teams))
    st.metric("Confrontos", len(st.session_state.matches))

if page == "Inscrição":
    st.header("Inscrição de equipe")
    st.write("Comece pelo nome da equipe, adicione os integrantes e marque o capitão.")

    name = st.text_input("Nome da equipe", max_chars=40, key="new_team_name")
    st.subheader("Integrantes")
    member_input_col, add_member_col = st.columns([5, 1])
    with member_input_col:
        st.text_input(
            "Nome do integrante",
            placeholder="Digite um nome e clique em +",
            key="new_member_input",
            label_visibility="collapsed",
        )
    with add_member_col:
        add_member = st.button("+", help="Adicionar integrante", use_container_width=True)

    if add_member:
        new_member = st.session_state.new_member_input.strip()
        if not new_member:
            st.error("Digite o nome do integrante antes de adicionar.")
        elif len(st.session_state.new_team_members) >= 12:
            st.error("O limite é de 12 integrantes por equipe.")
        elif any(member.casefold() == new_member.casefold() for member in st.session_state.new_team_members if member):
            st.error("Esse integrante já foi adicionado.")
        else:
            st.session_state.new_team_members.append(new_member)
            st.rerun()

    selected_captains = []
    for index, member in enumerate(st.session_state.new_team_members):
        if member:
            captain_col, name_col = st.columns([1, 8])
            with captain_col:
                is_captain = st.checkbox(
                    "Capitão",
                    key=f"captain_{index}",
                    help="Marque esta caixa para definir o capitão.",
                )
            with name_col:
                st.text_input(
                    f"Integrante {index + 1}",
                    value=member,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"display_member_{index}",
                )
            if is_captain:
                selected_captains.append(member)

    submitted = st.button("Inscrever equipe", type="primary", use_container_width=True)
    if submitted:
        clean_members = [member.strip() for member in st.session_state.new_team_members if member.strip()]
        if not name.strip():
            st.error("Preencha o nome da equipe.")
        elif len(clean_members) < 2:
            st.error("Adicione pelo menos dois integrantes.")
        elif len(selected_captains) != 1:
            st.error("Marque a caixa de exatamente um integrante para definir o capitão.")
        elif any(team["name"].casefold() == name.strip().casefold() for team in st.session_state.teams):
            st.error("Já existe uma equipe com esse nome.")
        else:
            st.session_state.teams.append(
                {
                    "id": st.session_state.next_team_id,
                    "name": name.strip(),
                    "members": clean_members,
                    "captain": selected_captains[0],
                }
            )
            st.session_state.next_team_id += 1
            st.session_state.new_team_members = [""]
            add_audit(f"Equipe {name.strip()} inscrita.")
            st.success(f"Equipe {name.strip()} inscrita com sucesso!")
            st.rerun()

    st.subheader("Equipes cadastradas")
    if not st.session_state.teams:
        st.info("Ainda não há equipes cadastradas.")
    else:
        for team in st.session_state.teams:
            with st.expander(f"{team['name']} — capitão: {team['captain']}"):
                st.write("Integrantes:", ", ".join(team["members"]))

elif page == "Confrontos e apostas":
    st.header("Confrontos e apostas")
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

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Sortear confrontos", type="primary", use_container_width=True):
            create_random_matches()
    with col_b:
        if st.button("Refazer sorteio", use_container_width=True):
            reset_matches()
            create_random_matches()

    if not st.session_state.matches:
        st.info("Cadastre as equipes e realize o sorteio para liberar as apostas.")
    else:
        render_bracket()
        st.metric("Saldo de pontos virtuais", points_for_user(user) if user else 1000)

        for match in st.session_state.matches:
            team_a = team_label(match["team_a"])
            team_b = team_label(match["team_b"])
            with st.container(border=True):
                st.subheader(f"{team_a}  ×  {team_b}")
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

        st.subheader("Gerenciar equipes")
        if not st.session_state.teams:
            st.info("Nenhuma equipe cadastrada.")
        elif st.session_state.matches:
            st.warning(
                "O chaveamento já foi criado. Cancele a rodada para editar as equipes; "
                "isso também apagará as apostas pendentes desta rodada."
            )
            if st.button("Cancelar chaveamento e liberar edição"):
                reset_matches()
                st.success("Chaveamento cancelado. Agora as equipes podem ser editadas.")
                st.rerun()
        else:
            st.caption("Exclua as equipes que não participarão antes de realizar o sorteio.")
            for team in st.session_state.teams:
                team_col, action_col = st.columns([5, 1])
                with team_col:
                    st.write(f"**{team['name']}** — capitão: {team['captain']}")
                with action_col:
                    if st.button("Excluir", key=f"delete_team_{team['id']}"):
                        delete_team(team["id"])
                        st.success(f"Equipe {team['name']} excluída.")
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
