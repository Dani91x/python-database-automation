interface FormStringProps {
  form: string;
  side: 'home' | 'away';
}

export function FormString({ form, side }: FormStringProps) {
  const isHome = side === 'home';
  
  if (!form) {
    return (
      <div className="glass-card p-4">
        <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-2 uppercase tracking-wider">
          League Form
        </h4>
        <p className="text-muted-foreground text-sm">N/D</p>
      </div>
    );
  }

  const formArray = form.split('');

  return (
    <div className="glass-card p-4">
      <h4 className="font-heading text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
        League Form
      </h4>
      <div className="flex flex-wrap gap-1.5">
        {formArray.map((result, index) => (
          <div
            key={index}
            className={`
              ${result === 'W' ? 'form-pill-w' : ''}
              ${result === 'D' ? 'form-pill-d' : ''}
              ${result === 'L' ? 'form-pill-l' : ''}
            `}
          >
            {result}
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground mt-3">
        Last {formArray.length} matches • 
        <span className="text-result-win ml-1">{formArray.filter(r => r === 'W').length}W</span>
        <span className="text-result-draw ml-1">{formArray.filter(r => r === 'D').length}D</span>
        <span className="text-result-loss ml-1">{formArray.filter(r => r === 'L').length}L</span>
      </p>
    </div>
  );
}
