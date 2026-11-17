# MASTER FISHING — versão inicial

Aplicação web de gestão de concursos de pesca, com autenticação, perfis Admin/User e permissões por evento.

## Conteúdo
- `app.py` — aplicação Streamlit.
- `schema.sql` — tabelas, funções e políticas de segurança Supabase.
- `requirements.txt` — dependências.
- `.streamlit/secrets.toml.example` — modelo de configuração.

## 1. Criar projeto Supabase
1. Criar um projeto em https://supabase.com/.
2. Abrir **SQL Editor**.
3. Executar todo o conteúdo de `schema.sql`.
4. Em **Project Settings > API**, copiar Project URL, anon/public key e service_role key.

## 2. Configurar Secrets
Criar `.streamlit/secrets.toml` localmente com:

```toml
SUPABASE_URL = "https://TEU-PROJETO.supabase.co"
SUPABASE_ANON_KEY = "A_TUA_ANON_KEY"
SUPABASE_SERVICE_ROLE_KEY = "A_TUA_SERVICE_ROLE_KEY"
```

Nunca publicar `secrets.toml` no GitHub. A `service_role` key é secreta e nunca deve ser colocada no código ou no browser.

## 3. Criar o primeiro Admin
1. No Supabase, abrir **Authentication > Users** e criar o teu utilizador com email e palavra-passe.
2. Confirmar que foi criada uma linha em `public.profiles`.
3. No SQL Editor, executar, substituindo pelo teu email:

```sql
update public.profiles
set role = 'admin', active = true
where email = 'O_TEU_EMAIL';
```

4. Iniciar sessão na aplicação.

## 4. Executar localmente
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 5. Publicar no Streamlit Community Cloud
1. Criar um repositório GitHub e carregar `app.py`, `requirements.txt` e `schema.sql`.
2. Criar uma aplicação em https://share.streamlit.io/.
3. Configurar os três Secrets no painel da aplicação.
4. Publicar.

## Segurança e limites desta versão
- A chave `service_role` é usada apenas no servidor Streamlit para criar contas e atribuir permissões. Nunca a expor no repositório.
- A leitura e operações normais usam a sessão autenticada do utilizador e políticas RLS.
- O Admin deve ser criado inicialmente pelo painel Supabase e promovido por SQL.
- Esta versão é a fundação de autenticação, eventos e acessos. Inscrições, sorteios, pesagens, classificações, upload de logótipos e relatórios serão desenvolvidos nas etapas seguintes.
- Antes de usar com dados reais, testar com contas separadas (Admin e User) e confirmar que um User não consegue consultar eventos não atribuídos.
