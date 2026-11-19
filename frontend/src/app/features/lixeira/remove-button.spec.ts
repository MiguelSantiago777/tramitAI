import { HttpErrorResponse } from '@angular/common/http';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { RemoveButton } from './remove-button';
import { TrashService } from './trash.service';

describe('RemoveButton', () => {
  let fixture: ComponentFixture<RemoveButton>;
  let api: { remove: ReturnType<typeof vi.fn>; restore: ReturnType<typeof vi.fn> };
  let answers: boolean[];

  async function setup(
    role = 'OWNER',
    remove: ReturnType<typeof vi.fn> = vi.fn(() => of(undefined)),
  ) {
    answers = [];
    api = { remove, restore: vi.fn(() => of(undefined)) };
    await TestBed.configureTestingModule({
      imports: [RemoveButton],
      providers: [
        provideRouter([{ path: '**', children: [] }]),
        { provide: TrashService, useValue: api },
        { provide: AuthService, useValue: { session: signal({ role }) } },
        {
          provide: MatDialog,
          useValue: { open: () => ({ afterClosed: () => of(answers.shift() ?? false) }) },
        },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(RemoveButton);
    fixture.componentRef.setInput('kind', 'client');
    fixture.componentRef.setInput('itemId', 'c1');
    fixture.componentRef.setInput('label', 'Ana');
    await fixture.whenStable();
  }

  const button = () => (fixture.nativeElement as HTMLElement).querySelector('button');

  it('só remove depois de confirmar', async () => {
    await setup();
    answers.push(false);
    button()?.click();
    expect(api.remove).not.toHaveBeenCalled();
    answers.push(true);
    button()?.click();
    expect(api.remove).toHaveBeenCalledWith('client', 'c1', false);
  });

  it('com parcelas em aberto pede a segunda confirmação e manda force', async () => {
    const remove = vi.fn((_kind: string, _id: string, force: boolean) =>
      force
        ? of(undefined)
        : throwError(
            () =>
              new HttpErrorResponse({
                status: 409,
                error: { error: { code: 'has_open_installments', message: '2 parcelas' } },
              }),
          ),
    );
    await setup('LAWYER', remove);
    answers.push(true, true);
    button()?.click();
    expect(remove).toHaveBeenLastCalledWith('client', 'c1', true);
  });

  it('a equipe não vê o botão', async () => {
    await setup('STAFF');
    expect(button()).toBeNull();
  });
});
