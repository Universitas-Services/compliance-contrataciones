from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class CAActoSeparadoAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.CA_ACTO_SEPARADO


class CAActoSeparadoJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.CA_ACTO_SEPARADO


CAActoSeparadoAgent = CAActoSeparadoAnalistaAgent
