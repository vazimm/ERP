from app import db


class Cliente(db.Model):
    """Modelo simples de cliente usado pelo dashboard.

    Campos:
      - id: PK
      - endereco: string
    """

    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    endereco = db.Column(db.String(255), nullable=False)
    enviroment = db.Column(db.String(100), nullable=False, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'endereco': self.endereco
        }
