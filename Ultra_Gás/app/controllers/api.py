from flask import Blueprint, jsonify, request, session, abort


api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/estoque', methods=['GET'])
def api_estoque():
    """Retorna dados simulados para o gráfico de estoque.

    Estrutura retornada:
    {
      "summary": { "statusText": "..." },
      "pie": { "p45": 10, "p20": 5, ... }
    }
    """
    # Requer usuário autenticado para acessar informações de estoque
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401
    # Tenta buscar dados reais do banco
    try:
        # Import dentro do bloco para evitar problemas de import circular na inicialização
        # e para só tentar acessar o DB quando este endpoint for chamado.
        from app.models.estoque import Estoque, DEFAULT_CAPACITY
        estoque = Estoque.query.first()
        if estoque:
            # Usa DEFAULT_CAPACITY (definido em app/models/estoque.py) para compor a mensagem.
            data = {
                "summary": {"statusText": f"Estoque: {estoque.total()} / {DEFAULT_CAPACITY} itens ({estoque.percent(DEFAULT_CAPACITY)}%)"},
                "pie": estoque.to_pie()
            }
            return jsonify(data)
    except Exception:
        # se houver qualquer problema com o DB, cai no mock abaixo
        pass

    # Fallback mock
    data = {
        "summary": {"statusText": "Mock: estoque equilibrado — itens com baixa quantidade: 3"},
        "pie": {
            "p45": 20,
            "p20": 20,
            "p13": 13,
            "p8": 8,
            "p5": 5,
            "agua": 15
        }
    }
    return jsonify(data)


@api_bp.route('/pedidos', methods=['POST'])
def api_pedidos():
    """Recebe um pedido do front-end, valida e grava como uma Entrega.

    Aceita payloads flexíveis:
      - já formatado: { endereco, destinatario, produto, metodo_pagamento }
      - ou raw: { endereco, cliente, produtos: [{nome,quantidade}], pagamentos: [metodo] }

    Retorna 201 com o registro salvo ou 400/500 em erro.
    """
    # Requer usuário autenticado para registrar pedidos
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Payload inválido'}), 400

    endereco = data.get('endereco') or data.get('rua')
    destinatario = data.get('destinatario') or data.get('cliente')

    # normalizar produto: pode vir como string ou como lista de objetos
    produto = data.get('produto')
    if not produto and isinstance(data.get('produtos'), list):
        parts = []
        for p in data.get('produtos'):
            nome = p.get('nome') if isinstance(p, dict) else None
            quantidade = p.get('quantidade') if isinstance(p, dict) else None
            if nome and quantidade:
                parts.append(f"{nome}:{quantidade}")
        produto = ', '.join(parts) if parts else None

    # normalizar método de pagamento (single)
    metodo = data.get('metodo_pagamento')
    if not metodo and isinstance(data.get('pagamentos'), list):
        metodo = data.get('pagamentos')[0] if len(data.get('pagamentos')) > 0 else None

    # validações básicas
    if not endereco or not destinatario:
        return jsonify({'error': 'Campos obrigatórios ausentes: endereco e destinatario'}), 400
    if not produto:
        return jsonify({'error': 'Nenhum produto informado'}), 400

    allowed = {'pix', 'a_prazo', 'cartao', 'dinheiro'}
    if metodo and metodo not in allowed:
        return jsonify({'error': 'metodo_pagamento inválido'}), 400

    # grava no banco
    try:
        from app import db
        from app.models.entregas import Entrega

        preco = data.get('preco') or ''

        entrega = Entrega(
            endereco=endereco,
            destinatario=destinatario,
            produto=produto,
            metodo_pagamento=metodo,
            encarregado='',   # inicia vazio
            entregue=False,   # inicia não entregue
            pago=False,        # inicia não pago
            preco=preco        # valor calculado pelo front-end
        )
        db.session.add(entrega)
        db.session.commit()

        return jsonify({'ok': True, 'entrega': entrega.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao gravar entrega', 'detail': str(e)}), 500


@api_bp.route('/financeiro', methods=['GET'])
def api_financeiro():
    """Retorna dados para o gráfico financeiro com base nas entregas.

    Conta quantas entregas (entregue=True) foram realizadas por cada método de pagamento.
    Estrutura retornada compatível com Chart.js (labels + datasets).
    """
    from sqlalchemy import func

    # Apenas usuários autenticados podem acessar dados financeiros
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401
    try:
        from app import db
        from app.models.entregas import Entrega

        # Métodos conhecidos e ordem fixa
        metodos_ordem = ["a_prazo", "pix", "cartao", "dinheiro"]
        counts_map = {m: 0 for m in metodos_ordem}

        resultados = db.session.query(Entrega.metodo_pagamento, func.count(Entrega.id)) \
            .filter(Entrega.metodo_pagamento.isnot(None), Entrega.entregue.is_(True)) \
            .group_by(Entrega.metodo_pagamento).all()

        for metodo, qtd in resultados:
            if metodo in counts_map:
                counts_map[metodo] = qtd

        data = {
            "labels": ["A prazo", "Pix", "Cartão", "Dinheiro"],
            "datasets": [
                {
                    "data": [counts_map["a_prazo"], counts_map["pix"], counts_map["cartao"], counts_map["dinheiro"]],
                    "backgroundColor": ["#4dc9f6", "#f67019", "#f53794", "#537bc4"]
                }
            ]
        }
        return jsonify(data)
    except Exception:
        # Fallback simples se ocorrer erro com o DB
        data = {
            "labels": ["A prazo", "Pix", "Cartão", "Dinheiro"],
            "datasets": [
                {
                    "data": [0, 0, 0, 0],
                    "backgroundColor": ["#4dc9f6", "#f67019", "#f53794", "#537bc4"]
                }
            ],
            "summary": {"status": "Falha ao acessar entregas; retornando zeros."}
        }
        return jsonify(data)


@api_bp.route('/clientes', methods=['POST'])
def api_clientes_create():
    """Cria um novo cliente a partir do payload { endereco: '...' }.

    Retorna 201 com o cliente criado ou 400/500 em caso de falha.
    """
    # Requer usuário autenticado para criar clientes
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    if not isinstance(data, dict):
        return jsonify({'error': 'Payload inválido'}), 400

    endereco = data.get('endereco')
    if not endereco or not str(endereco).strip():
        return jsonify({'error': 'Campo endereco é obrigatório'}), 400

    try:
        from app import db
        from app.models.clientes import Cliente

        cliente = Cliente(endereco=str(endereco).strip())
        db.session.add(cliente)
        db.session.commit()

        return jsonify({'ok': True, 'cliente': cliente.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao criar cliente', 'detail': str(e)}), 500


@api_bp.route('/entregas/<int:entrega_id>/confirm', methods=['POST'])
def api_entrega_confirm(entrega_id):
    """Marca uma entrega como entregue (entregue=True). Retorna registro atualizado."""
    # Requer usuário autenticado para confirmar entregas
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        from app import db
        from app.models.entregas import Entrega
        entrega = Entrega.query.get(entrega_id)
        if not entrega:
            return jsonify({'error': 'Entrega não encontrada'}), 404
        entrega.entregue = True
        db.session.commit()
        return jsonify({'ok': True, 'entrega': entrega.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao confirmar entrega', 'detail': str(e)}), 500


@api_bp.route('/entregas/<int:entrega_id>/retirar', methods=['POST'])
def api_entrega_retirar(entrega_id):
    """Atribui a entrega ao usuário logado (encarregado) e baixa o estoque.

    Momento da baixa de estoque: quando o usuário "retira" o pedido para entrega.

    Regras:
      - Requer sessão com user_name.
      - Se entrega já tiver encarregado diferente, retorna 409.
      - Se encarregado estiver vazio ou igual ao usuário, tenta atribuir e baixar estoque.
      - Campo produto da entrega é uma string no formato "agua:2, p45:1".
    """

    def _parse_produtos(produto_str):
        """Converte a string de produtos em um dicionário de quantidades.

        Exemplo de entrada: "agua:2, p45:1" -> {"agua": 2, "p45": 1}
        Ignora partes vazias e quantidades inválidas (<=0).
        """
        result = {}
        if not produto_str:
            return result
        for part in produto_str.split(','):
            part = part.strip()
            if not part:
                continue
            if ':' not in part:
                continue
            tipo, qtd_str = part.split(':', 1)
            tipo = (tipo or '').strip().lower()
            qtd_str = (qtd_str or '').strip()
            if not tipo or not qtd_str:
                continue
            try:
                qtd = int(qtd_str)
            except ValueError:
                continue
            if qtd <= 0:
                continue
            # acumula se houver repetição do mesmo tipo
            result[tipo] = result.get(tipo, 0) + qtd
        return result

    user_name = session.get('user_name')
    if not user_name:
        return jsonify({'error': 'Usuário não autenticado'}), 401
    try:
        from app import db
        from app.models.entregas import Entrega
        from app.models.estoque import Estoque

        entrega = Entrega.query.get(entrega_id)
        if not entrega:
            return jsonify({'error': 'Entrega não encontrada'}), 404

        # Se já atribuída a outro usuário, não permite retirar
        if entrega.encarregado and entrega.encarregado != user_name:
            return jsonify({'error': 'Entrega já atribuída', 'encarregado': entrega.encarregado}), 409

        # Carrega registro de estoque
        estoque = Estoque.query.first()
        if not estoque:
            return jsonify({'error': 'Estoque não configurado'}), 500

        # Se a entrega já estiver atribuída ao mesmo usuário, não baixa estoque de novo
        if entrega.encarregado == user_name:
            return jsonify({'ok': True, 'entrega': entrega.to_dict(), 'warning': 'Entrega já atribuída a este usuário. Nenhuma nova baixa de estoque executada.'})

        itens = _parse_produtos(entrega.produto)

        # Mapeia chaves de produto para campos do modelo Estoque
        campo_map = {
            'p45': 'p45',
            'p20': 'p20',
            'p13': 'p13',
            'p8': 'p8',
            'p5': 'p5',
            'agua': 'agua',
        }

        # Validação de estoque suficiente
        for tipo, qtd in itens.items():
            campo = campo_map.get(tipo)
            if not campo:
                # Produto desconhecido, ignora na baixa mas avisa
                continue
            atual = getattr(estoque, campo) or 0
            if atual < qtd:
                return jsonify({'error': f'Estoque insuficiente para {tipo}. Disponível: {atual}, necessário: {qtd}'}), 400

        # Aplica baixa
        for tipo, qtd in itens.items():
            campo = campo_map.get(tipo)
            if not campo:
                continue
            atual = getattr(estoque, campo) or 0
            setattr(estoque, campo, atual - qtd)

        # Atribui entrega ao usuário
        entrega.encarregado = user_name

        db.session.commit()
        return jsonify({'ok': True, 'entrega': entrega.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao retirar entrega', 'detail': str(e)}), 500


@api_bp.route('/entregas/<int:entrega_id>/pagar', methods=['POST'])
def api_entrega_pagar(entrega_id):
    """Marca uma entrega como paga (pago=True) somente se já estiver entregue."""
    # Requer usuário autenticado para registrar pagamento
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        from app import db
        from app.models.entregas import Entrega
        entrega = Entrega.query.get(entrega_id)
        if not entrega:
            return jsonify({'error': 'Entrega não encontrada'}), 404
        if not entrega.entregue:
            return jsonify({'error': 'Entrega ainda não marcada como entregue'}), 400
        entrega.pago = True
        db.session.commit()
        return jsonify({'ok': True, 'entrega': entrega.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao marcar pagamento', 'detail': str(e)}), 500


@api_bp.route('/themes', methods=['GET'])
def api_list_themes():
    """Lista as variáveis de cor agrupadas por tema.

    Retorno:
    {
      "root": {"cor-fundo": "#ffffff", ...},
      "rosa": {"cor-fundo": "#ffcbcd", ...},
      ...
    }
    Usa valor_atual se existir, senão valor_padrao.
    As cores são filtradas pelo campo enviroment, que deve
    corresponder ao enviroment do usuário logado. Se não houver
    usuário logado ou nenhuma cor para aquele enviroment, volta
    para as cores globais (enviroment NULL).
    """
    # Requer usuário autenticado para consultar temas do ambiente
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    try:
        from app.models.color import Color

        temas = {}

        # Ambiente do usuário logado
        env = session.get('enviroment')

        # 1) tenta buscar cores específicas do ambiente
        cores = []
        if env:
            cores = Color.query.filter_by(enviroment=env).all()

        # 2) se não encontrou cores específicas, usa cores globais (enviroment NULL)
        if not cores:
            cores = Color.query.filter(Color.enviroment.is_(None)).all()

        for c in cores:
            tema = c.tema or 'root'
            if tema not in temas:
                temas[tema] = {}
            temas[tema][c.nome_variavel] = c.valor_atual or c.valor_padrao

        return jsonify(temas)
    except Exception as e:
        return jsonify({'error': 'Falha ao buscar temas', 'detail': str(e)}), 500


@api_bp.route('/themes/<tema>/apply', methods=['POST'])
def api_apply_theme(tema):
    """Define o tema atual na sessão do usuário.

    O front-end deve ler esse tema e requisitar /api/themes
    para obter as variáveis e aplicá-las via CSS custom properties.
    """
    # Requer usuário autenticado para aplicar tema na sessão
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    tema = (tema or '').strip().lower()
    if not tema:
        return jsonify({'error': 'Tema inválido'}), 400

    # Apenas grava na sessão; a aplicação do tema é via JS/CSS.
    session['current_theme'] = tema
    return jsonify({'ok': True, 'tema': tema})


@api_bp.route('/themes/custom', methods=['POST'])
def api_create_custom_theme():
    """Cria ou atualiza um tema para o ambiente do usuário de ambiente.

    Espera JSON:
    {
      "tema": "nome_tema",
      "cores": {
         "cor-fundo": "#ffffff",
         ...
      }
    }
    Remove entradas anteriores com mesmo (enviroment, tema) e recria.
    """
    from app import db
    from app.models.color import Color

    # Requer usuário autenticado e ambiente definido na sessão
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    env = session.get('enviroment')
    if not env:
        return jsonify({'error': 'Ambiente não encontrado na sessão'}), 401

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    tema = (data.get('tema') or '').strip()
    cores = data.get('cores') or {}

    if not tema:
        return jsonify({'error': 'Campo tema é obrigatório'}), 400
    if not isinstance(cores, dict) or not cores:
        return jsonify({'error': 'Campo cores é obrigatório'}), 400

    try:
        # Remove qualquer tema anterior com mesmo nome para este ambiente
        Color.query.filter_by(enviroment=env, tema=tema).delete()

        # Cria novas entradas para cada variável de cor
        novos = []
        for nome_var, valor in cores.items():
            if not valor:
                continue
            novos.append(
                Color(
                    nome_variavel=nome_var,
                    valor_padrao=str(valor),
                    tema=tema,
                    enviroment=env,
                )
            )

        if not novos:
            return jsonify({'error': 'Nenhuma cor válida informada'}), 400

        db.session.add_all(novos)
        db.session.commit()
        return jsonify({'ok': True, 'tema': tema}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao salvar tema', 'detail': str(e)}), 500


@api_bp.route('/themes/list-names', methods=['GET'])
def api_list_theme_names():
    """Lista apenas os nomes de tema disponíveis para o ambiente do usuário."""
    from app import db
    from app.models.color import Color

    # Requer usuário autenticado para listar temas do ambiente
    if not session.get('user_id'):
        return jsonify({'temas': []}), 401

    env = session.get('enviroment')
    if not env:
        return jsonify({'temas': []})

    try:
        rows = (
            db.session.query(Color.tema)
            .filter(Color.enviroment == env)
            .distinct()
            .all()
        )
        temas = sorted({r[0] for r in rows if r[0]})
        return jsonify({'temas': list(temas)})
    except Exception as e:
        return jsonify({'error': 'Falha ao listar temas', 'detail': str(e)}), 500


@api_bp.route('/themes/apply-to-env', methods=['POST'])
def api_apply_theme_to_env():
    """Define o tema para todos os usuários de um mesmo enviroment.

    Espera JSON: { "tema": "nome_tema" }
    Atualiza User.tema de todos os usuários com User.enviroment == env atual.
    """
    from app import db
    from app.models.users import User

    # Requer usuário autenticado e ambiente definido
    if not session.get('user_id'):
        return jsonify({'error': 'Usuário não autenticado'}), 401

    env = session.get('enviroment')
    if not env:
        return jsonify({'error': 'Ambiente não encontrado na sessão'}), 401

    try:
        data = request.get_json(force=True) or {}
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400

    tema = (data.get('tema') or '').strip()
    if not tema:
        return jsonify({'error': 'Campo tema é obrigatório'}), 400

    try:
        db.session.query(User).filter(User.enviroment == env).update({User.tema: tema})
        db.session.commit()
        # Também salva na sessão do usuário atual
        session['current_theme'] = tema
        return jsonify({'ok': True, 'tema': tema})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify({'error': 'Falha ao aplicar tema ao ambiente', 'detail': str(e)}), 500


@api_bp.route('/current-theme', methods=['GET'])
def api_current_theme():
    """Retorna o tema atual do usuário (coluna User.tema), com fallback para 'root'."""
    from app.models.users import User

    user_id = session.get('user_id')
    if not user_id:
        # se não logado, usa tema salvo na sessão (se houver) ou root
        tema = session.get('current_theme') or 'root'
        return jsonify({'tema': tema})

    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'tema': 'root'})
        return jsonify({'tema': user.tema or 'root'})
    except Exception:
        return jsonify({'tema': 'root'})
