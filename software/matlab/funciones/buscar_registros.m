function codigos = buscar_registros()
% BUSCAR_REGISTROS  Codes of every sensor log datos/presion/crudos/R_<code>.csv, oldest first (with or
% without video). Includes the empty-room reference (e.g. 20260824_1400_00_07, 0 robots, no mode).
    f = dir(fullfile(raiz_proyecto(), 'datos', 'presion', 'crudos', 'R_*.csv'));
    codigos = {};
    for i = 1:numel(f)
        tok = regexp(f(i).name, '^R_(\d{8}_\d{4}_\d{2}[A-Za-z]{0,2}_\d{1,4})\.csv$', 'tokens', 'once');
        if ~isempty(tok), codigos{end + 1} = tok{1}; end %#ok<AGROW>
    end
    codigos = unique(codigos);
end
