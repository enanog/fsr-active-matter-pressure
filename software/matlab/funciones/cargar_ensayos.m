function D = cargar_ensayos(filtros)
% CARGAR_ENSAYOS  Load the trials whose code contains any of the texts in FILTROS
% (cell, e.g. {'20260924', '20261030_1600'}). 'todos' = every trial; {} = pick from a list.
% Returns a struct array (see cargar_ensayo), oldest first.
    todos = buscar_ensayos();
    if isempty(todos)
        error('No hay trayectorias en datos/video/trayectorias.');
    end
    if nargin < 1, filtros = {}; end
    codigos = elegir_codigos(todos, filtros, 'Ensayos a graficar:');
    for i = 1:numel(codigos)
        Di = cargar_ensayo(codigos{i});
        if i == 1, D = Di; else, D(i) = Di; end
    end
end
