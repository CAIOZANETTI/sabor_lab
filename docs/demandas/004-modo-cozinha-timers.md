# [SaborLab] Modo cozinha com cronograma paralelo e timers

## Responsável, branch e dependência

Claude Code, em `claude/cook-mode`, depois da integração da demanda 003. Abrir
PR e não fazer merge.

## Objetivo

Transformar o `RecipeProcess` e o cronograma do scheduler em uma interface de
execução na cozinha, sem entrada textual. A pessoa deve saber:

- o que separar e cortar antes de começar;
- quando ligar o forno ou aquecer a panela;
- o que fazer agora, em seguida e em paralelo;
- quanto falta para cada timer e para a refeição;
- quando verificar temperatura, textura ou aparência;
- quando uma etapa precisa descansar;
- como reagir a adiantamentos, atrasos e etapas puladas.

## Referência de UX

Criar `site/cozinhar.html` e ligar a partir de `site/app.html`. O modo precisa ter
duas telas principais:

### 1. Antes de cozinhar

- duração total, tempo ativo e passivo;
- equipamentos necessários;
- ingredientes agrupados por estação;
- mise en place com cortes, quantidades e recipientes;
- tarefas antecipáveis;
- alertas de segurança e descanso;
- botão único `Tudo pronto — começar`.

### 2. Durante o preparo

- cartão grande `Agora`;
- cartões menores `Em paralelo` e `Depois`;
- cronograma por faixas: cozinheiro, forno, fogão, bancada/descanso;
- timers associados às etapas;
- temperatura alvo, faixa e sinal sensorial de conclusão;
- ações apenas por botões: iniciar, pausar, concluir, +1 min, +5 min, pular;
- progresso da receita e previsão atualizada de serviço.

Não incluir chat, prompt ou campo de texto.

## Regras dos timers

- Usar timestamps (`Date.now`) como fonte de verdade, não apenas decrementar um
  contador por `setInterval`, para evitar deriva em abas suspensas.
- Persistir estado localmente com versão do esquema e `recipe_process_id`.
- Recuperar timers após recarregar ou reabrir a página.
- Permitir pausa apenas quando a etapa realmente puder ser pausada; forno e
  descanso podem continuar correndo mesmo se a interface estiver pausada.
- Solicitar notificação do navegador somente após ação explícita e funcionar sem
  permissão.
- Usar Wake Lock quando disponível, com fallback claro.
- Áudio/vibração precisam de controle para silenciar.
- Nunca iniciar timer de segurança automaticamente antes da confirmação da etapa.
- Ao atrasar uma etapa, pedir escolha entre `recalcular cronograma` e `manter
  horário de serviço`; ambas sem texto livre.

## Máquina de estados

```text
pending → ready → running → completed
                    ├────→ paused → running
                    └────→ skipped
```

Transições inválidas devem ser rejeitadas. `completed` e `skipped` precisam de
registro de horário. Etapas dependentes só ficam `ready` quando suas condições
forem atendidas.

## Dados apresentados

- duração planejada e real;
- tempo ativo/passivo;
- equipamento e capacidade reservada;
- ingredientes e quantidades da etapa;
- técnica e corte com explicação curta;
- temperatura em °C;
- sinal verificável: cor, textura, temperatura interna ou redução;
- transformação esperada;
- fonte de segurança quando aplicável.

Não mostrar precisão que os dados não sustentam. “Fogo médio” continua uma
instrução qualitativa se não houver medição real.

## Acessibilidade e responsividade

- tela utilizável com uma mão em celular;
- alvos de toque mínimos e modo de alto contraste;
- teclado completo em desktop;
- `aria-live` para alertas sem repetir o contador a cada segundo;
- nenhuma informação apenas por cor;
- opção de reduzir animações;
- idioma português e números/unidades locais.

## Privacidade

O estado fica no dispositivo no MVP. Não enviar hábitos, horários ou dados de
saúde para servidor. Incluir botão `Apagar sessão de cozinha`.

## Testes obrigatórios

### Unidade

1. Timer usa timestamp e não deriva após suspensão simulada.
2. Estado persiste e restaura com tempo correto.
3. Transições inválidas são rejeitadas.
4. Dependências controlam quando uma tarefa fica pronta.
5. Atraso atualiza previsão e tarefas dependentes.
6. Duas etapas paralelas mantêm timers independentes.
7. Timer passivo continua quando a interface troca de etapa.

### Navegador/Playwright

1. Fluxo completo sem mouse e sem campo de texto.
2. Mise en place inicia o modo cozinha.
3. Preaquecimento e corte aparecem em paralelo.
4. `+1 min`, pausa permitida e conclusão funcionam.
5. Recarregar recupera a sessão.
6. Negar notificações não quebra o preparo.
7. Layout funciona em 360 px e desktop.
8. Build do Pages inclui `cozinhar.html`.

## Caso de aceite demonstrativo

Usar um processo criado na demanda 003 com:

- ligar forno antecipadamente;
- cortar vegetais enquanto o forno aquece;
- marinada ou descanso passivo;
- etapa de frigideira que ocupa o cozinheiro;
- cocção no forno;
- molho preparado em paralelo;
- descanso final antes de servir.

O cronograma precisa mostrar redução real de duração em comparação com a soma
sequencial e explicar quais tarefas foram paralelizadas.

## Fora de escopo

- controlar forno ou fogão remotamente;
- reconhecimento de voz;
- câmera ou visão computacional;
- backend, contas ou sincronização entre dispositivos;
- inventar etapas ausentes;
- substituir termômetro ou práticas de segurança.

## Critérios de aceite

- [ ] Nenhuma entrada textual no modo cozinha.
- [ ] Mise en place e cocção são fases distintas.
- [ ] Tarefas paralelas e recursos são compreensíveis.
- [ ] Timers sobrevivem a recarga e suspensão.
- [ ] Segurança, descanso e reações aparecem com fonte/contexto.
- [ ] Interface acessível e responsiva.
- [ ] Testes de unidade, integração e navegador passam.
- [ ] Nenhum dado demonstrativo é apresentado como cálculo real.

## Entrega

Commits separados para máquina de estados/timers, UI, persistência e testes.
Documentar limitações dos navegadores e não modificar o scheduler para acomodar
atalhos de interface sem revisão do contrato.
