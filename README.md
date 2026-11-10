# Arena Cup

MVP em Streamlit para inscrição de equipes, sorteio de confrontos e apostas com pontos virtuais.

## Executar

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

## Fluxo

1. Cadastre as equipes, seus integrantes e o capitão.
2. Em **Confrontos e apostas**, realize o sorteio aleatório.
3. Apostadores identificam-se e usam um saldo inicial de 1.000 pontos virtuais.
4. Em **Painel administrativo**, entre com a senha de demonstração `admin123` e lance os resultados.

Os resultados administrativos liquidam as apostas e ficam no log de auditoria.

Antes de publicar, configure a variável de ambiente `ADMIN_PASSWORD` com uma senha
forte. O app não possui uma senha administrativa padrão: se essa variável não estiver
configurada, o painel administrativo permanecerá bloqueado.

> Este MVP é demonstrativo: não processa dinheiro real e não deve ser usado para ocultar
> manipulação de resultados. Qualquer correção de resultado deve ser justificada e auditada.
