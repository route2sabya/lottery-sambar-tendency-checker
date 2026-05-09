# Lottery Ticket Probability Scoring Approach

## Overview
This document describes the statistical model used in the `lottery_by_chance` project to score and calculate win probabilities for lottery ticket numbers. The approach is based on historical data analysis and does not use machine learning; instead, it employs empirical statistics with recency adjustments.

## Data Structure
- **Historical Data**: CSV file (`historical_data.csv`) with columns: `date`, `digit_length`, `winning_number`.
- **Digit Lengths Supported**: 4, 5, 6, 8 (representing different lottery types).
- **Assumptions**: Each draw is independent, but historical patterns influence probability estimates.

## Scoring Metrics

### 1. Empirical Probability
- **Formula**: `empirical_prob = count_of_wins / total_draws`
- **Description**: The raw frequency of the ticket number appearing in historical draws.
- **Range**: 0.0 to 1.0 (but typically very low for large number spaces).
- **Purpose**: Measures how "hot" a number has been based on past wins.

### 2. Theoretical Probability
- **Formula**: `theoretical_prob = 1 / max_possible_numbers`
- **Max Possible**: `10 ** digit_length` (e.g., 10,000 for 4-digit, 1,000,000 for 6-digit).
- **Description**: The baseline probability assuming all numbers are equally likely (true randomness).
- **Purpose**: Provides a sanity check and upper bound for adjusted probabilities.

### 3. Recency Factor
- **Calculation**:
  - Compute average repeat interval: Mean days between consecutive wins for all numbers.
  - For a specific number: `days_since_last_win / avg_repeat_interval`
  - Cap at 2.0 (to avoid over-weighting very old numbers).
- **Description**: Adjusts for "due" numbers—those that haven't won recently may have slightly higher probability.
- **Purpose**: Incorporates time-based patterns, assuming numbers cycle in popularity.

### 4. Adjusted Probability
- **Formula**: `adjusted_prob = min(empirical_prob * recency_factor, theoretical_prob)`
- **Description**: Combines empirical frequency with recency, but caps at theoretical to prevent unrealistic estimates.
- **Range**: 0.0 to theoretical_prob.
- **Purpose**: The final score for win probability, balancing historical data with randomness.

## Additional Outputs
- **Times Won**: Total historical wins for the number.
- **Days Since Last Win**: How long ago it last appeared (None if never).

## Limitations
- **No Causality**: Lotteries are random; past performance doesn't guarantee future results.
- **Data Dependency**: Accuracy relies on comprehensive historical data.
- **Simplifications**: Recency model is basic; doesn't account for trends, seasonality, or external factors.
- **Not Predictive**: This is descriptive statistics, not a predictive model.

## Usage in Code
See `lottery_calculator.py` for implementation. The `calculate_probability()` method computes all metrics for a given ticket number and digit length.

## Example
For a 6-digit number that won 2 times in 365 draws, last won 50 days ago, with avg repeat interval 30 days:
- Empirical: 2/365 ≈ 0.0055
- Recency Factor: min(50/30, 2.0) = 1.67
- Adjusted: min(0.0055 * 1.67, 1e-6) ≈ 9.18e-6
- Theoretical: 1e-6

This approach provides a data-driven estimate while acknowledging lottery randomness.