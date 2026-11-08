import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';
import AdvisorMarkdown from './AdvisorMarkdown';

it('renders Markdown headings, emphasis, lists, tables, and verified source citations', () => {
  render(
    <AdvisorMarkdown
      sources={[{ id: 'S1', url: 'https://example.com/menu' }]}
      content={
        '## Increase savings\n\n**Dining** increased by $50.\n\n- Set a monthly goal\n- Review subscriptions\n\n| Category | Change |\n| --- | --- |\n| Dining | $50 |\n\nCheck [S1] and [the menu](https://example.com/menu). Unknown [S2].\n\n`[S1]`'
      }
    />,
  );
  expect(
    screen.getByRole('heading', { name: 'Increase savings' }),
  ).toBeInTheDocument();
  expect(
    screen.getByText('Dining', { selector: 'strong' }),
  ).toBeInTheDocument();
  expect(screen.getAllByRole('listitem')).toHaveLength(2);
  expect(screen.getByRole('table')).toHaveTextContent('Dining');
  expect(screen.getByRole('link', { name: '[S1]' })).toHaveAttribute(
    'href',
    'https://example.com/menu',
  );
  expect(screen.getByRole('link', { name: 'the menu' })).toHaveAttribute(
    'rel',
    'noreferrer noopener',
  );
  expect(screen.queryByRole('link', { name: '[S2]' })).not.toBeInTheDocument();
  expect(screen.getByText('[S1]', { selector: 'code' })).toBeInTheDocument();
});
it('never fetches images or exposes unapproved financial URLs and ignores raw HTML', () => {
  const { container } = render(
    <AdvisorMarkdown
      content={
        '![tracker](https://search.brave.com/search?q=PRIVATE_BALANCE)\n\n[Search](https://search.brave.com/search?q=PRIVATE_BALANCE) [bad](javascript:alert(1))\n\n<script>alert(1)</script><img src="https://example.com/private"><iframe src="https://example.com"></iframe>\n\n**Safe text**'
      }
    />,
  );
  expect(container.querySelectorAll('img,iframe,script,a')).toHaveLength(0);
  expect(screen.getByText('Safe text')).toBeInTheDocument();
  expect(screen.getByText('Search')).toBeInTheDocument();
});

it('renders local-model currency and common TeX prose legibly without altering literal code or ordinary prices', () => {
  const { container } = render(
    <AdvisorMarkdown
      content={
        String.raw`Action: Review **Whole Foods** ($\text{average} \approx $270.00$ per month) and Costco ($\text{average} \approx $44.51$ per month).

Prices: $50 and $75. Escaped price: \$12.00.` + '\n\n`$\\text{average}$`'
      }
    />,
  );
  expect(container).toHaveTextContent(
    'Whole Foods (average ≈ $270.00 per month)',
  );
  expect(container).toHaveTextContent('Costco (average ≈ $44.51 per month)');
  expect(container).toHaveTextContent(
    'Prices: $50 and $75. Escaped price: $12.00.',
  );
  expect(container.querySelector('code')).toHaveTextContent(
    '$\\text{average}$',
  );
});
