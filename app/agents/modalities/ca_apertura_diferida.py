from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class CAAperturaDiferidaAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA


class CAAperturaDiferidaJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.CA_ACTO_UNICO_APERTURA_DIFERIDA


CAAperturaDiferidaAgent = CAAperturaDiferidaAnalistaAgent
