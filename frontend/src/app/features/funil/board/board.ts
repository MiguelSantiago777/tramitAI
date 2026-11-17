import {
  CdkDragDrop,
  DragDropModule,
  moveItemInArray,
  transferArrayItem,
} from '@angular/cdk/drag-drop';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { debounceTime, merge } from 'rxjs';

import { toApiError } from '../../../core/http/api-error';
import { initialsOf } from '../../../shared/initials';
import {
  AREA_LABELS,
  BoardSummary,
  Opportunity,
  STAGES,
  SOURCE_LABELS,
  Stage,
  money,
} from '../funil.models';
import { FunilService } from '../funil.service';
import { OpportunityDialog } from '../opportunity-dialog/opportunity-dialog';
import { LostReasonDialog } from './lost-reason-dialog';

interface Column {
  id: Stage;
  label: string;
  hint: string;
  items: Opportunity[];
}

const SOURCE_ICONS: Record<string, string> = {
  WHATSAPP: 'chat',
  INDICACAO: 'handshake',
  REDES: 'thumb_up',
  SITE: 'language',
  PRESENCIAL: 'storefront',
  OUTRA: 'more_horiz',
};

/** Funil de novos clientes em quadro (arraste os cartões entre as etapas). */
@Component({
  selector: 'app-board',
  imports: [
    DragDropModule,
    ReactiveFormsModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatProgressBarModule,
  ],
  templateUrl: './board.html',
  styleUrl: './board.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Board {
  private readonly api = inject(FunilService);
  private readonly dialog = inject(MatDialog);

  readonly who = new FormControl('', { nonNullable: true });
  readonly search = new FormControl('', { nonNullable: true });
  readonly columns = signal<Column[]>(STAGES.map((s) => ({ ...s, items: [] })));
  readonly summary = signal<BoardSummary | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  readonly money = money;
  readonly conversion = computed(() => {
    const rate = this.summary()?.conversion_rate;
    return rate === null || rate === undefined ? '—' : `${Math.round(rate * 100)}%`;
  });

  constructor() {
    merge(this.who.valueChanges, this.search.valueChanges.pipe(debounceTime(300)))
      .pipe(takeUntilDestroyed())
      .subscribe(() => this.load());
    this.load();
  }

  areaLabel(o: Opportunity): string {
    return o.area ? AREA_LABELS[o.area] : '';
  }

  sourceIcon(o: Opportunity): string {
    return SOURCE_ICONS[o.source] ?? 'more_horiz';
  }

  sourceLabel(o: Opportunity): string {
    return SOURCE_LABELS[o.source];
  }

  initials(name: string): string {
    return initialsOf(name);
  }

  daysInStage(o: Opportunity): number {
    const ms = Date.now() - new Date(o.stage_changed_at).getTime();
    return Math.max(0, Math.floor(ms / 86_400_000));
  }

  columnValue(col: Column): string {
    const total = col.items.reduce((sum, o) => sum + Number(o.estimated_value ?? 0), 0);
    return total > 0 ? money(total) : '';
  }

  create(): void {
    this.openDialog(undefined);
  }

  open(o: Opportunity): void {
    this.openDialog(o);
  }

  drop(event: CdkDragDrop<Opportunity[]>, stage: Stage): void {
    const item = event.previousContainer.data[event.previousIndex];
    if (event.previousContainer === event.container) {
      if (event.previousIndex === event.currentIndex) {
        return;
      }
      moveItemInArray(event.container.data, event.previousIndex, event.currentIndex);
    } else {
      transferArrayItem(
        event.previousContainer.data,
        event.container.data,
        event.previousIndex,
        event.currentIndex,
      );
    }
    this.columns.update((cols) => [...cols]);
    if (stage === 'LOST' && item.stage !== 'LOST') {
      this.dialog
        .open(LostReasonDialog, { width: '520px', maxWidth: '95vw' })
        .afterClosed()
        .subscribe((reason?: string) => {
          if (reason) {
            this.persist(item, stage, event.currentIndex, reason);
          } else {
            this.load(); // desistiu: volta o cartão
          }
        });
      return;
    }
    this.persist(item, stage, event.currentIndex);
  }

  private persist(item: Opportunity, stage: Stage, position: number, reason = ''): void {
    this.api.move(item.id, stage, position, reason).subscribe({
      next: () => this.load(),
      error: (err: unknown) => {
        this.error.set(toApiError(err).message);
        this.load();
      },
    });
  }

  private openDialog(opportunity: Opportunity | undefined): void {
    this.dialog
      .open(OpportunityDialog, {
        data: { opportunity },
        width: '680px',
        maxWidth: '95vw',
        autoFocus: 'first-tabbable',
      })
      .afterClosed()
      .subscribe((saved?: Opportunity) => {
        if (saved) {
          this.load();
        }
      });
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.board({ owner: this.who.value, q: this.search.value.trim() }).subscribe({
      next: (items) => {
        this.loading.set(false);
        this.columns.set(
          STAGES.map((s) => ({
            ...s,
            items: items.filter((o) => o.stage === s.id).sort((a, b) => a.position - b.position),
          })),
        );
      },
      error: (err: unknown) => {
        this.loading.set(false);
        this.error.set(toApiError(err).message);
      },
    });
    this.api.summary().subscribe({
      next: (s) => this.summary.set(s),
      error: () => this.summary.set(null),
    });
  }
}
