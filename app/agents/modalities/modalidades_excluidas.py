from app.agents.modalities.base import BaseAnalistaAgent, BaseJuridicoAgent
from app.models.schemas import Modalidad


class ModalidadesExcluidasAnalistaAgent(BaseAnalistaAgent):
    modalidad = Modalidad.MODALIDADES_EXCLUIDAS


class ModalidadesExcluidasJuridicoAgent(BaseJuridicoAgent):
    modalidad = Modalidad.MODALIDADES_EXCLUIDAS


ModalidadesExcluidasAgent = ModalidadesExcluidasAnalistaAgent
