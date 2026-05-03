import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Exception } from '../../models/exception.model';

@Component({
  selector: 'app-live-event-stream',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './live-event-stream.component.html',
})
export class LiveEventStreamComponent {
  @Input() exceptions: Exception[] = [];

  get recent(): Exception[] {
    return [...this.exceptions].reverse().slice(0, 40);
  }

  severityClass(severity: string | null): string {
    const map: Record<string, string> = {
      low:      'bg-green-100 text-green-700',
      medium:   'bg-yellow-100 text-yellow-700',
      high:     'bg-orange-100 text-orange-700',
      critical: 'bg-red-100 text-red-700',
    };
    return map[severity ?? ''] || 'bg-gray-100 text-gray-500';
  }

  statusDotPulse(status: string): boolean {
    return !['resolved', 'failed'].includes(status);
  }

  statusTextClass(status: string): string {
    const map: Record<string, string> = {
      detecting: 'text-blue-500', analyzing: 'text-violet-500', deciding: 'text-amber-500',
      communicating: 'text-emerald-500', acting: 'text-rose-500',
      resolved: 'text-green-600', failed: 'text-red-500',
    };
    return map[status] || 'text-gray-400';
  }
}
