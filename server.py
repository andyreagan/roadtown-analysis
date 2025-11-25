#!/usr/bin/env python3
"""
Simple Flask server for race results data
"""

from flask import Flask, jsonify, send_file, request
import json
import re

app = Flask(__name__)


def parse_time(time_str):
    """Convert time string (MM:SS.S or H:MM:SS.S) to seconds"""
    if not time_str or time_str.strip() == '':
        return None

    try:
        parts = time_str.split(':')
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        elif len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except:
        return None
    return None


def load_raw_results(year):
    """Load raw results for a specific year"""
    results = []
    filename = f'data/results-{year}.txt'

    try:
        with open(filename, 'r') as f:
            lines = f.readlines()

            # Skip header
            for line in lines[1:]:
                if not line.strip():
                    continue

                # Split by tabs
                parts = line.strip().split('\t')
                if len(parts) < 9:
                    continue

                try:
                    age = int(parts[4])
                    sex = parts[5]
                    division = parts[6] if len(parts) > 6 else ''
                    gun_time = parts[7]
                    div_place = parts[2] if len(parts) > 2 else ''

                    # Only process M and F with valid times
                    if sex in ['M', 'F']:
                        time_seconds = parse_time(gun_time)
                        if time_seconds:
                            results.append({
                                'name': parts[3],
                                'age': age,
                                'sex': sex,
                                'division': division,
                                'div_place': div_place,
                                'time_seconds': time_seconds,
                                'time_display': gun_time,
                                'year': year
                            })
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        print(f"Warning: {filename} not found")

    return results


def load_race_data(year='2025'):
    """Load and process race results"""
    results = load_raw_results(year)

    # Determine which years to include for all-time Pareto (all years up to and including current)
    all_time_years = []
    if year == '2025':
        all_time_years = ['2023', '2024', '2025']
    elif year == '2024':
        all_time_years = ['2023', '2024']
    else:  # 2023
        all_time_years = ['2023']

    # Load all data for all-time Pareto
    all_time_male_results = []
    all_time_female_results = []

    for hist_year in all_time_years:
        hist_results = load_raw_results(hist_year)
        all_time_male_results.extend([r for r in hist_results if r['sex'] == 'M'])
        all_time_female_results.extend([r for r in hist_results if r['sex'] == 'F'])

    # Separate by sex first
    male_results = [r for r in results if r['sex'] == 'M']
    female_results = [r for r in results if r['sex'] == 'F']

    def get_fastest_at_each_age(runners):
        """For all-time analysis: keep only the fastest runner at each age"""
        if not runners:
            return []

        # Group by age and keep only the fastest at each age
        age_groups = {}
        for runner in runners:
            age = runner['age']
            if age not in age_groups or runner['time_seconds'] < age_groups[age]['time_seconds']:
                age_groups[age] = runner

        return list(age_groups.values())

    def compute_pareto_front(runners):
        """
        Compute Pareto front: the optimal age-performance curve.
        - From young to peak: times decrease (getting faster)
        - Peak age: fastest time overall
        - From peak to old: times increase (getting slower)
        """
        if not runners:
            return []

        # Find the fastest runner (peak performance)
        fastest_runner = min(runners, key=lambda x: x['time_seconds'])
        peak_age = fastest_runner['age']

        # Sort by age
        sorted_runners = sorted(runners, key=lambda x: x['age'])

        # Split into before and after peak
        younger_than_peak = [r for r in sorted_runners if r['age'] < peak_age]
        at_or_older_than_peak = [r for r in sorted_runners if r['age'] >= peak_age]

        pareto = []

        # For younger ages: include if faster than all younger runners (times decreasing)
        best_time_so_far = float('inf')
        for runner in younger_than_peak:
            if runner['time_seconds'] < best_time_so_far:
                pareto.append(runner)
                best_time_so_far = runner['time_seconds']

        # For peak and older ages: include if faster than all older runners (times increasing)
        # Process from oldest to peak
        best_time_so_far = float('inf')
        older_pareto = []
        for runner in reversed(at_or_older_than_peak):
            if runner['time_seconds'] < best_time_so_far:
                older_pareto.append(runner)
                best_time_so_far = runner['time_seconds']

        # Add older_pareto in correct order (youngest to oldest)
        pareto.extend(reversed(older_pareto))

        return pareto

    male_pareto = compute_pareto_front(male_results)
    female_pareto = compute_pareto_front(female_results)

    # Compute all-time Pareto fronts if we have historical data
    # First, keep only the fastest runner at each age across all years
    male_all_time_pareto = []
    female_all_time_pareto = []
    if all_time_male_results:
        fastest_male_by_age = get_fastest_at_each_age(all_time_male_results)
        male_all_time_pareto = compute_pareto_front(fastest_male_by_age)
    if all_time_female_results:
        fastest_female_by_age = get_fastest_at_each_age(all_time_female_results)
        female_all_time_pareto = compute_pareto_front(fastest_female_by_age)

    # Find age group winners (div_place == '1')
    age_group_winners = []
    age_group_winner_set = set()
    for result in results:
        if result['div_place'] == '1' and result['division']:
            key = (result['name'], result['age'], result['sex'])
            age_group_winner_set.add(key)
            age_group_winners.append({
                'name': result['name'],
                'age': result['age'],
                'sex': result['sex'],
                'division': result['division'],
                'time_display': result['time_display']
            })

    # Sort by division name
    age_group_winners.sort(key=lambda x: (x['sex'], x['division']))

    # Create sets for quick lookup
    male_pareto_set = set((r['name'], r['age'], r['time_seconds']) for r in male_pareto)
    female_pareto_set = set((r['name'], r['age'], r['time_seconds']) for r in female_pareto)

    # Function to interpolate Pareto front time at a given age
    def get_pareto_time_at_age(age, pareto_front):
        """Get the Pareto front time at a specific age (with interpolation)"""
        if not pareto_front:
            return None

        # Find exact match
        for p in pareto_front:
            if p['age'] == age:
                return p['time_seconds']

        # Find surrounding ages for interpolation
        younger = [p for p in pareto_front if p['age'] < age]
        older = [p for p in pareto_front if p['age'] > age]

        if not younger and not older:
            return None
        elif not younger:
            # Age is younger than all Pareto points, use youngest
            return min(pareto_front, key=lambda x: x['age'])['time_seconds']
        elif not older:
            # Age is older than all Pareto points, use oldest
            return max(pareto_front, key=lambda x: x['age'])['time_seconds']
        else:
            # Interpolate between closest younger and older
            closest_younger = max(younger, key=lambda x: x['age'])
            closest_older = min(older, key=lambda x: x['age'])

            # Linear interpolation
            age_diff = closest_older['age'] - closest_younger['age']
            time_diff = closest_older['time_seconds'] - closest_younger['time_seconds']
            age_offset = age - closest_younger['age']

            return closest_younger['time_seconds'] + (time_diff * age_offset / age_diff)

    # Function to calculate blocking runners
    def count_blocking_runners(runner, all_runners_same_gender):
        """
        Count how many runners need to be removed for this runner to be on Pareto front.
        For younger than peak: count runners who are younger AND faster
        For older than peak: count runners who are older AND faster
        """
        # Find the peak (fastest runner)
        fastest = min(all_runners_same_gender, key=lambda x: x['time_seconds'])
        peak_age = fastest['age']

        blocking_count = 0

        if runner['age'] < peak_age:
            # Younger than peak: count runners who are younger OR same age AND faster
            for other in all_runners_same_gender:
                if other['age'] <= runner['age'] and other['time_seconds'] < runner['time_seconds']:
                    blocking_count += 1
        elif runner['age'] > peak_age:
            # Older than peak: count runners who are older OR same age AND faster
            for other in all_runners_same_gender:
                if other['age'] >= runner['age'] and other['time_seconds'] < runner['time_seconds']:
                    blocking_count += 1
        else:
            # At peak age: check if they're the fastest
            if runner['time_seconds'] == fastest['time_seconds']:
                blocking_count = 0
            else:
                # Count faster runners at same age
                blocking_count = sum(1 for other in all_runners_same_gender
                                   if other['age'] == runner['age'] and other['time_seconds'] < runner['time_seconds'])

        return blocking_count

    # Prepare all data with distance to Pareto front and blocking count
    male_data = []
    female_data = []

    for result in male_results:
        pareto_time = get_pareto_time_at_age(result['age'], male_pareto)
        distance = result['time_seconds'] - pareto_time if pareto_time else None
        blocking = count_blocking_runners(result, male_results)

        male_data.append({
            'age': result['age'],
            'time_seconds': result['time_seconds'],
            'time_display': result['time_display'],
            'name': result['name'],
            'distance_to_pareto': distance,
            'blocking_runners': blocking
        })

    for result in female_results:
        pareto_time = get_pareto_time_at_age(result['age'], female_pareto)
        distance = result['time_seconds'] - pareto_time if pareto_time else None
        blocking = count_blocking_runners(result, female_results)

        female_data.append({
            'age': result['age'],
            'time_seconds': result['time_seconds'],
            'time_display': result['time_display'],
            'name': result['name'],
            'distance_to_pareto': distance,
            'blocking_runners': blocking
        })

    # Convert Pareto fronts to same format
    male_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name']
    } for r in male_pareto]

    female_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name']
    } for r in female_pareto]

    # Prepare Pareto front winners list with age group winner flag
    pareto_winners = []
    pareto_runner_set = set()

    for r in male_pareto:
        key = (r['name'], r['age'], 'M')
        pareto_runner_set.add(key)
        is_age_group_winner = key in age_group_winner_set
        pareto_winners.append({
            'name': r['name'],
            'age': r['age'],
            'sex': 'M',
            'time_display': r['time_display'],
            'is_age_group_winner': is_age_group_winner
        })
    for r in female_pareto:
        key = (r['name'], r['age'], 'F')
        pareto_runner_set.add(key)
        is_age_group_winner = key in age_group_winner_set
        pareto_winners.append({
            'name': r['name'],
            'age': r['age'],
            'sex': 'F',
            'time_display': r['time_display'],
            'is_age_group_winner': is_age_group_winner
        })

    # Sort by sex then age
    pareto_winners.sort(key=lambda x: (x['sex'], x['age']))

    # Update age group winners with Pareto flag
    for winner in age_group_winners:
        key = (winner['name'], winner['age'], winner['sex'])
        winner['is_pareto'] = key in pareto_runner_set

    # Create Pareto-adjusted rankings (all runners by distance to Pareto)
    all_runners_adjusted = []

    for result in male_data:
        all_runners_adjusted.append({
            'name': result['name'],
            'age': result['age'],
            'sex': 'M',
            'time_display': result['time_display'],
            'time_seconds': result['time_seconds'],
            'distance_to_pareto': result['distance_to_pareto'] if result['distance_to_pareto'] is not None else 0,
            'blocking_runners': result['blocking_runners']
        })

    for result in female_data:
        all_runners_adjusted.append({
            'name': result['name'],
            'age': result['age'],
            'sex': 'F',
            'time_display': result['time_display'],
            'time_seconds': result['time_seconds'],
            'distance_to_pareto': result['distance_to_pareto'] if result['distance_to_pareto'] is not None else 0,
            'blocking_runners': result['blocking_runners']
        })

    # Sort by distance to Pareto front first, then by actual time
    # This puts all Pareto winners (#1) at top sorted by their race time
    all_runners_adjusted.sort(key=lambda x: (x['distance_to_pareto'], x['time_seconds']))

    # Format all-time Pareto data with year information and mark new records
    male_all_time_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name'],
        'year': r.get('year', 'Unknown'),
        'is_current_year': r.get('year') == year
    } for r in male_all_time_pareto]

    female_all_time_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['name'],
        'year': r.get('year', 'Unknown'),
        'is_current_year': r.get('year') == year
    } for r in female_all_time_pareto]

    return {
        'male_all': male_data,
        'female_all': female_data,
        'male_pareto': male_pareto_data,
        'female_pareto': female_pareto_data,
        'male_all_time_pareto': male_all_time_pareto_data,
        'female_all_time_pareto': female_all_time_pareto_data,
        'age_group_winners': age_group_winners,
        'pareto_winners': pareto_winners,
        'pareto_adjusted_rankings': all_runners_adjusted
    }


@app.route('/')
def index():
    return send_file('race_chart_2025.html')


@app.route('/2025')
def index_2025():
    return send_file('race_chart_2025.html')


@app.route('/2023')
def index_2023():
    return send_file('race_chart_2023.html')


@app.route('/2024')
def index_2024():
    return send_file('race_chart_2024.html')


@app.route('/all-time')
def index_all_time():
    return send_file('race_chart_all_time.html')


@app.route('/data')
def get_data():
    year = request.args.get('year', '2025')
    return jsonify(load_race_data(year))


@app.route('/data/all-time')
def get_all_time_data():
    """Load all years combined for all-time view"""
    all_years = ['2023', '2024', '2025']

    # Load all results from all years
    all_results = []
    for year in all_years:
        year_results = load_raw_results(year)
        all_results.extend(year_results)

    # Detect duplicate names and add year suffix if needed
    name_year_counts = {}
    for result in all_results:
        name = result['name']
        if name not in name_year_counts:
            name_year_counts[name] = []
        name_year_counts[name].append(result['year'])

    # Add year to display name if person appears in multiple years
    for result in all_results:
        name = result['name']
        if len(set(name_year_counts[name])) > 1:
            result['display_name'] = f"{name} ({result['year']})"
        else:
            result['display_name'] = name

    # Separate by sex
    male_results = [r for r in all_results if r['sex'] == 'M']
    female_results = [r for r in all_results if r['sex'] == 'F']

    # For all-time, get fastest at each age then compute Pareto
    def get_fastest_at_each_age(runners):
        if not runners:
            return []
        age_groups = {}
        for runner in runners:
            age = runner['age']
            if age not in age_groups or runner['time_seconds'] < age_groups[age]['time_seconds']:
                age_groups[age] = runner
        return list(age_groups.values())

    def compute_pareto_front(runners):
        if not runners:
            return []
        fastest = min(runners, key=lambda x: x['time_seconds'])
        peak_age = fastest['age']
        sorted_runners = sorted(runners, key=lambda x: x['age'])
        younger_than_peak = [r for r in sorted_runners if r['age'] < peak_age]
        at_or_older_than_peak = [r for r in sorted_runners if r['age'] >= peak_age]
        pareto = []
        best_time_so_far = float('inf')
        for runner in younger_than_peak:
            if runner['time_seconds'] < best_time_so_far:
                pareto.append(runner)
                best_time_so_far = runner['time_seconds']
        best_time_so_far = float('inf')
        older_pareto = []
        for runner in reversed(at_or_older_than_peak):
            if runner['time_seconds'] < best_time_so_far:
                older_pareto.append(runner)
                best_time_so_far = runner['time_seconds']
        pareto.extend(reversed(older_pareto))
        return pareto

    fastest_male_by_age = get_fastest_at_each_age(male_results)
    fastest_female_by_age = get_fastest_at_each_age(female_results)
    male_pareto = compute_pareto_front(fastest_male_by_age)
    female_pareto = compute_pareto_front(fastest_female_by_age)

    # Format data for display
    male_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in male_results]

    female_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in female_results]

    male_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in male_pareto]

    female_pareto_data = [{
        'age': r['age'],
        'time_seconds': r['time_seconds'],
        'time_display': r['time_display'],
        'name': r['display_name'],
        'year': r['year']
    } for r in female_pareto]

    # Create Pareto winners list (all runners on Pareto front)
    pareto_winners = []
    for r in male_pareto:
        pareto_winners.append({
            'name': r['display_name'],
            'age': r['age'],
            'sex': 'M',
            'time_display': r['time_display'],
            'year': r['year']
        })
    for r in female_pareto:
        pareto_winners.append({
            'name': r['display_name'],
            'age': r['age'],
            'sex': 'F',
            'time_display': r['time_display'],
            'year': r['year']
        })

    # Sort by sex then age
    pareto_winners.sort(key=lambda x: (x['sex'], x['age']))

    return jsonify({
        'male_all': male_data,
        'female_all': female_data,
        'male_pareto': male_pareto_data,
        'female_pareto': female_pareto_data,
        'pareto_winners': pareto_winners
    })


if __name__ == '__main__':
    print("Starting Multi-Year Flask server...")
    print("2023: http://localhost:5000/2023")
    print("2024: http://localhost:5000/2024")
    print("2025: http://localhost:5000 (default)")
    print("All-Time: http://localhost:5000/all-time")
    app.run(debug=True, port=5000)
