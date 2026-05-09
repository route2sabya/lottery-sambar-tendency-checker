import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random

def generate_sample_data(digit_lengths=[4, 5, 6, 8], days=365):
    """Generate sample historical lottery data for the last 'days' days."""
    start_date = datetime.now() - timedelta(days=days)
    data = []

    for i in range(days):
        date = start_date + timedelta(days=i)
        for length in digit_lengths:
            # Generate a random winning number for each digit length each day
            winning_number = ''.join(random.choices('0123456789', k=length))
            data.append({
                'date': date.strftime('%Y-%m-%d'),
                'digit_length': length,
                'winning_number': winning_number
            })

    df = pd.DataFrame(data)
    df.to_csv('historical_data.csv', index=False)
    print(f"Generated {len(df)} records in historical_data.csv")
    return df

if __name__ == "__main__":
    generate_sample_data()