import pandas as pd
import numpy as np
from datetime import datetime
from collections import defaultdict, Counter

class LotteryProbabilityCalculator:
    def __init__(self, data_file='historical_data.csv'):
        self.data = pd.read_csv(data_file)
        self.data['date'] = pd.to_datetime(self.data['date'])
        self.digit_lengths = sorted(self.data['digit_length'].unique())
        self.analysis = self._analyze_data()

    def _analyze_data(self):
        """Analyze historical data for each digit length."""
        analysis = {}
        for length in self.digit_lengths:
            df = self.data[self.data['digit_length'] == length]
            total_draws = len(df)

            # Count frequency of each number
            number_counts = Counter(df['winning_number'])
            unique_numbers = len(number_counts)

            # Calculate repeat statistics
            repeat_intervals = []
            last_seen = {}
            for _, row in df.sort_values('date').iterrows():
                num = row['winning_number']
                if num in last_seen:
                    interval = (row['date'] - last_seen[num]).days
                    repeat_intervals.append(interval)
                last_seen[num] = row['date']

            analysis[length] = {
                'total_draws': total_draws,
                'unique_numbers': unique_numbers,
                'number_counts': number_counts,
                'repeat_intervals': repeat_intervals,
                'avg_repeat_interval': np.mean(repeat_intervals) if repeat_intervals else None,
                'max_possible': 10 ** length
            }
        return analysis

    def calculate_probability(self, ticket_number, digit_length):
        """Calculate win probability for a given ticket number."""
        if digit_length not in self.analysis:
            return None

        info = self.analysis[digit_length]
        total_draws = info['total_draws']
        max_possible = info['max_possible']

        # Empirical probability based on historical frequency
        count = info['number_counts'].get(ticket_number, 0)
        empirical_prob = count / total_draws if total_draws > 0 else 0

        # Adjust for recency (numbers that haven't won recently might be "due")
        last_win = None
        for _, row in self.data[(self.data['digit_length'] == digit_length) & (self.data['winning_number'] == ticket_number)].iterrows():
            last_win = row['date']
        days_since_last_win = (datetime.now() - last_win).days if last_win else None

        # Simple model: higher prob if not seen recently, but cap at theoretical
        if days_since_last_win and info['avg_repeat_interval']:
            recency_factor = min(days_since_last_win / info['avg_repeat_interval'], 2.0)
        else:
            recency_factor = 1.0

        adjusted_prob = min(empirical_prob * recency_factor, 1.0 / max_possible)

        return {
            'empirical_probability': empirical_prob,
            'adjusted_probability': adjusted_prob,
            'times_won': count,
            'days_since_last_win': days_since_last_win,
            'theoretical_probability': 1.0 / max_possible
        }

def main():
    print("Lottery Probability Calculator")
    print("Loading historical data...")

    try:
        calc = LotteryProbabilityCalculator()
    except FileNotFoundError:
        print("Error: historical_data.csv not found. Run generate_data.py first.")
        return

    print(f"Available digit lengths: {calc.digit_lengths}")

    digit_length = int(input("Enter digit length (4, 5, 6, or 8): "))
    if digit_length not in calc.digit_lengths:
        print("Invalid digit length.")
        return

    ticket = input(f"Enter your {digit_length}-digit ticket number: ")
    if len(ticket) != digit_length or not ticket.isdigit():
        print("Invalid ticket number.")
        return

    prob = calc.calculate_probability(ticket, digit_length)
    if prob:
        print("\nResults:")
        print(f"Times won historically: {prob['times_won']}")
        print(f"Days since last win: {prob['days_since_last_win'] or 'Never'}")
        print(f"Empirical probability: {prob['empirical_probability']:.6f}")
        print(f"Adjusted probability: {prob['adjusted_probability']:.6f}")
        print(f"Theoretical probability: {prob['theoretical_probability']:.6f}")
    else:
        print("Could not calculate probability.")

if __name__ == "__main__":
    main()