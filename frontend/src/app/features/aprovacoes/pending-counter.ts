import { Injectable, inject, signal } from '@angular/core';

import { DraftsService } from './drafts.service';

/** Quantidade de rascunhos aguardando aprovação, para o selo do menu. */
@Injectable({ providedIn: 'root' })
export class PendingDraftsCounter {
  private readonly drafts = inject(DraftsService);
  readonly count = signal(0);

  refresh(): void {
    this.drafts.list({ status: 'DRAFT' }, 0, 1).subscribe({
      next: (page) => this.count.set(page.count),
      error: () => undefined,
    });
  }
}
