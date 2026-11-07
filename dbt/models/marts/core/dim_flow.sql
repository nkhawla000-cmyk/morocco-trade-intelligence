select *
from (
    values
        ('X', 'Export', 'Exportations'),
        ('M', 'Import', 'Importations')
) as flows (flow_code, flow_name, flow_name_fr)
