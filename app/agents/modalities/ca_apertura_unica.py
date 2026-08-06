from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class CAAperturaUnicaAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.CA_ACTO_UNICO_APERTURA_UNICA


class CAAperturaUnicaJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.CA_ACTO_UNICO_APERTURA_UNICA


# Compat: nombre histórico = Analista
CAAperturaUnicaAgent = CAAperturaUnicaAnalistaAgent
