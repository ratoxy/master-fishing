import os
from datetime import date
import streamlit as st
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

st.set_page_config(page_title="MASTER FISHING", page_icon="🎣", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.5rem; max-width: 1200px;}
div[data-testid="stMetric"] {background: rgba(128,128,128,.08); padding: 12px; border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

def get_secret(name: str, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)

SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = get_secret("SUPABASE_SERVICE_ROLE_KEY")

def get_client() -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    tokens = st.session_state.get("tokens")
    if tokens:
        try:
            client.auth.set_session(tokens["access_token"], tokens["refresh_token"])
        except Exception:
            st.session_state.pop("tokens", None)
            st.session_state.pop("user", None)
    return client

def get_admin_client() -> Client:
    # Esta chave fica exclusivamente no servidor (Streamlit Secrets).
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def audit(client, action, event_id=None, details=None):
    try:
        client.table("audit_log").insert({
            "event_id": event_id,
            "action": action,
            "details": details or {}
        }).execute()
    except Exception:
        # O registo de auditoria não deve interromper uma operação válida.
        pass

def logout():
    st.session_state.pop("tokens", None)
    st.session_state.pop("user", None)
    st.rerun()

def login_screen():
    st.title("🎣 MASTER FISHING")
    st.caption("Plataforma de gestão de concursos de pesca")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Palavra-passe", type="password")
        submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if submitted:
        if not email or not password:
            st.error("Introduz o email e a palavra-passe.")
            return
        try:
            client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
            response = client.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state["tokens"] = {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token
            }
            st.session_state["user"] = {
                "id": response.user.id,
                "email": response.user.email
            }
            st.rerun()
        except Exception:
            st.error("Não foi possível iniciar sessão. Confirma os dados ou contacta o administrador.")

def load_profile(client, user_id):
    result = client.table("profiles").select("id,email,display_name,role,active").eq("id", user_id).single().execute()
    return result.data

def show_admin_users(client, admin):
    st.subheader("Centro de gestão de utilizadores")
    st.caption("Cria contas e atribui os eventos em que cada colaborador pode trabalhar.")
    events = client.table("events").select("id,name,event_date,status").order("created_at", desc=True).execute().data or []
    users = client.table("profiles").select("id,email,display_name,role,active").order("email").execute().data or []

    with st.expander("Criar utilizador", expanded=False):
        with st.form("create_user"):
            email = st.text_input("Email do utilizador")
            display_name = st.text_input("Nome a apresentar")
            password = st.text_input("Palavra-passe inicial", type="password", help="Define uma palavra-passe temporária e entrega-a ao utilizador por um canal seguro.")
            selected_events = st.multiselect(
                "Eventos a que terá acesso",
                options=[e["id"] for e in events],
                format_func=lambda eid: next((f"{e['name']} — {e.get('event_date') or 'Sem data'}" for e in events if e["id"] == eid), eid)
            )
            create = st.form_submit_button("Criar utilizador", type="primary")
        if create:
            if not email or not password or len(password) < 8:
                st.error("Indica um email e uma palavra-passe com pelo menos 8 caracteres.")
            else:
                try:
                    admin_client = get_admin_client()
                    created = admin_client.auth.admin.create_user({
                        "email": email.strip(),
                        "password": password,
                        "email_confirm": True,
                        "user_metadata": {"display_name": display_name.strip()}
                    })
                    new_id = created.user.id
                    admin_client.table("profiles").upsert({
                        "id": new_id, "email": email.strip(),
                        "display_name": display_name.strip(), "role": "user", "active": True
                    }).execute()
                    if selected_events:
                        admin_client.table("event_access").insert([
                            {"event_id": eid, "user_id": new_id, "can_edit": True, "can_export": True}
                            for eid in selected_events
                        ]).execute()
                    audit(client, "user_created", details={"email": email.strip(), "event_count": len(selected_events)})
                    st.success("Utilizador criado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível criar o utilizador. Verifica se o email já existe e as configurações. Detalhe: {str(exc)[:250]}")

    st.markdown("**Utilizadores existentes**")
    if not users:
        st.info("Ainda não existem utilizadores adicionais.")
    for user in users:
        if user["id"] == admin["id"]:
            continue
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 2, 2])
            c1.write(f"**{user.get('display_name') or user['email']}**")
            c1.caption(user["email"])
            c2.write("Ativo" if user["active"] else "Inativo")
            access = client.table("event_access").select("event_id,can_edit,can_export").eq("user_id", user["id"]).execute().data or []
            c3.write(f"{len(access)} evento(s)")
            with st.expander("Gerir acessos"):
                current_ids = [a["event_id"] for a in access]
                selected = st.multiselect(
                    "Eventos autorizados",
                    options=[e["id"] for e in events],
                    default=current_ids,
                    format_func=lambda eid: next((e["name"] for e in events if e["id"] == eid), eid),
                    key=f"access_{user['id']}"
                )
                active = st.checkbox("Conta ativa", value=user["active"], key=f"active_{user['id']}")
                if st.button("Guardar permissões", key=f"save_{user['id']}"):
                    try:
                        admin_client = get_admin_client()
                        admin_client.table("event_access").delete().eq("user_id", user["id"]).execute()
                        if selected:
                            admin_client.table("event_access").insert([
                                {"event_id": eid, "user_id": user["id"], "can_edit": True, "can_export": True}
                                for eid in selected
                            ]).execute()
                        admin_client.table("profiles").update({"active": active}).eq("id", user["id"]).execute()
                        audit(client, "user_access_updated", details={"user_id": user["id"], "event_ids": selected, "active": active})
                        st.success("Permissões atualizadas.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Erro ao atualizar permissões: {str(exc)[:250]}")

def show_event_create(client):
    st.subheader("Criar novo evento")
    with st.form("new_event"):
        name = st.text_input("Nome da prova", placeholder="Ex.: 1.º MASTER CAPEC 2027")
        organization = st.text_input("Organização / equipa", placeholder="Ex.: CAPEC")
        event_date = st.date_input("Data do evento", value=None)
        location = st.text_input("Local", placeholder="Rio / albufeira / localidade")
        description = st.text_area("Observações", height=80)
        submitted = st.form_submit_button("Criar evento", type="primary")
    if submitted:
        if not name.strip() or not organization.strip():
            st.error("O nome da prova e a organização são obrigatórios.")
        else:
            try:
                result = client.table("events").insert({
                    "name": name.strip(),
                    "organization_name": organization.strip(),
                    "event_date": event_date.isoformat() if event_date else None,
                    "location": location.strip(),
                    "description": description.strip(),
                    "status": "setup"
                }).execute()
                audit(client, "event_created", event_id=result.data[0]["id"], details={"name": name.strip()})
                st.success("Evento criado com sucesso.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível criar o evento: {str(exc)[:250]}")

def show_event(client, event, can_edit, can_export):
    st.header(event["name"])
    st.caption(f"{event.get('organization_name') or ''} · {event.get('event_date') or 'Data por definir'} · {event.get('location') or 'Local por definir'}")
    if event.get("description"):
        st.write(event["description"])
    participants = client.table("participants").select("id", count="exact").eq("event_id", event["id"]).execute()
    col1, col2, col3 = st.columns(3)
    col1.metric("Inscritos", participants.count or 0)
    col2.metric("Estado", event.get("status", "setup").upper())
    col3.metric("Permissão", "Edição" if can_edit else "Consulta")
    st.info("A área de inscrições, sorteios, pesagens e classificações será acrescentada nas próximas etapas. A estrutura deste evento já está criada.")
    if can_edit:
        with st.expander("Editar dados do evento"):
            with st.form(f"edit_event_{event['id']}"):
                name = st.text_input("Nome da prova", value=event["name"])
                org = st.text_input("Organização", value=event.get("organization_name") or "")
                loc = st.text_input("Local", value=event.get("location") or "")
                desc = st.text_area("Observações", value=event.get("description") or "")
                save = st.form_submit_button("Guardar alterações")
            if save:
                try:
                    client.table("events").update({
                        "name": name.strip(), "organization_name": org.strip(),
                        "location": loc.strip(), "description": desc.strip()
                    }).eq("id", event["id"]).execute()
                    audit(client, "event_updated", event_id=event["id"])
                    st.success("Evento atualizado.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Erro ao guardar: {str(exc)[:250]}")

def main():
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        st.error("Falta configurar SUPABASE_URL e SUPABASE_ANON_KEY nos Secrets.")
        st.code('SUPABASE_URL = "https://....supabase.co"\nSUPABASE_ANON_KEY = "..."')
        st.stop()
    if not st.session_state.get("user"):
        login_screen()
        return

    try:
        client = get_client()
        user = st.session_state["user"]
        profile = load_profile(client, user["id"])
        if not profile or not profile["active"]:
            st.error("A tua conta está desativada. Contacta o administrador.")
            if st.button("Sair"):
                logout()
            st.stop()
    except Exception:
        st.error("A sessão expirou ou a conta não está configurada. Volta a iniciar sessão.")
        if st.button("Voltar ao login"):
            logout()
        st.stop()

    with st.sidebar:
        st.title("🎣 MASTER FISHING")
        st.caption(profile.get("display_name") or profile["email"])
        st.caption("ADMINISTRADOR" if profile["role"] == "admin" else "COLABORADOR")
        if st.button("Terminar sessão", use_container_width=True):
            logout()

    if profile["role"] == "admin":
        tabs = st.tabs(["Os meus eventos", "Criar evento", "Gestão de utilizadores"])
        with tabs[0]:
            events = client.table("events").select("*").order("created_at", desc=True).execute().data or []
            st.subheader("Todos os eventos")
            if not events:
                st.info("Ainda não existem eventos. Cria o primeiro no separador «Criar evento».")
            for event in events:
                with st.container(border=True):
                    a, b = st.columns([4, 1])
                    a.write(f"**{event['name']}**")
                    a.caption(f"{event.get('organization_name') or ''} · {event.get('event_date') or 'Sem data'} · {event.get('status')}")
                    if b.button("Abrir", key=f"open_admin_{event['id']}"):
                        st.session_state["selected_event"] = event["id"]
                        st.rerun()
            selected_id = st.session_state.get("selected_event")
            selected_event = next((e for e in events if e["id"] == selected_id), None)
            if selected_event:
                st.divider()
                if st.button("← Voltar à lista"):
                    st.session_state.pop("selected_event", None)
                    st.rerun()
                show_event(client, selected_event, True, True)
        with tabs[1]:
            show_event_create(client)
        with tabs[2]:
            show_admin_users(client, profile)
    else:
        access = client.table("event_access").select("event_id,can_edit,can_export,events(*)").eq("user_id", profile["id"]).execute().data or []
        st.title("Os meus eventos")
        if not access:
            st.info("Ainda não tens eventos atribuídos. Contacta o administrador.")
        for item in access:
            event = item.get("events")
            if not event:
                continue
            with st.container(border=True):
                st.write(f"**{event['name']}**")
                st.caption(f"{event.get('organization_name') or ''} · {event.get('event_date') or 'Sem data'}")
                if st.button("Abrir evento", key=f"open_user_{event['id']}"):
                    st.session_state["selected_event"] = event["id"]
                    st.rerun()
        selected_id = st.session_state.get("selected_event")
        selected = next((x for x in access if x.get("events") and x["events"]["id"] == selected_id), None)
        if selected:
            st.divider()
            if st.button("← Voltar aos meus eventos"):
                st.session_state.pop("selected_event", None)
                st.rerun()
            show_event(client, selected["events"], selected["can_edit"], selected["can_export"])

if __name__ == "__main__":
    main()
