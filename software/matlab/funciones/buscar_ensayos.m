function codigos = buscar_ensayos()
% BUSCAR_ENSAYOS  Codes of the trials with VidFetch trajectories (VP_<code>_robots.csv), oldest first.
% A split recording (VP_<code>(1)_robots.csv, (2)...) counts as one trial.
    f = dir(fullfile(raiz_proyecto(), 'datos', 'video', 'trayectorias', 'VP_*_robots.csv'));
    codigos = {};
    for i = 1:numel(f)
        tok = regexp(f(i).name, '^VP_(.+?)(\(\d+\))?_robots\.csv$', 'tokens', 'once');
        if ~isempty(tok)
            codigos{end+1} = tok{1}; %#ok<AGROW>
        end
    end
    codigos = unique(codigos);      % AAAAMMDD_HHMM: alphabetical = chronological
end
