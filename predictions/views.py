from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from bs4 import BeautifulSoup
import requests
from scipy.stats import poisson
import math
import json
from django.core.mail import send_mail
from django.views import View
from datetime import datetime, date
from .models import Prediction as LP
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import auth
from rest_framework import status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from .utils import fetch_data, calculate_poisson_probs, predict_match_result, get_top_probable_scorelines
from rest_framework.views import APIView
from django.core.cache import cache


# In-memory storage for league data
league_data = {}

# Create your views here.

# bot = telegram.Bot(token='settings.TELE_API_KEY')


# def home(request):
#     visitor_ip = visitor_ip = request.META.get('REMOTE_ADDR')
#     x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
#     if x_forwarded_for:
#         # The IP addresses are usually comma-separated.
#         ip_list = x_forwarded_for.split(',')
#         # The client's IP address is the first in the list.
#         visitor_ip = ip_list[0].strip()
#     else:
#         # If 'HTTP_X_FORWARDED_FOR' is not present, use 'REMOTE_ADDR'.
#         visitor_ip = request.META.get('REMOTE_ADDR')

#     # current_datetime = datetime.now()
#     current_datetime = datetime.today().strftime("%d %b, %y %H:%M:%S")
#     send_mail(
#         'New Visitor',
#         'A visitor ' + visitor_ip + ' has been on scoracle at ' + current_datetime,
#         'settings.EMAIL_HOST_USER',
#         ['mezardini@gmail.com'],
#         fail_silently=False,
#     )
#     predictions = 'No Predictions Available'
#     context = {'predictions': predictions}
#     return render(request, 'scoracle.html', context)


def win_probability(league, first_item, second_item):
    base_url = 'https://www.soccerstats.com/'

    # league = 'england2'
    home_away_url = f'{base_url}homeaway.asp?league={league}'
    home_away_soup = fetch_data(home_away_url)
    # if not home_away_soup:
    #     continue

    div_h2h_team1 = home_away_soup.find("div", {"id": "h2h-team1"})

    # Find the table within the div
    tablex = div_h2h_team1.find("table", {"id": "btable"})

    # Extract header and rows
    header = [th.text.strip() for th in tablex.find_all("th")]

    rows = [row.find_all('td') for row in tablex.find_all("tr")[1:]]
    team_data = {'header': header, 'rows': [
        [col.text.strip() for col in row] for row in rows[1:]]}
    # print(team_data)

    # Perform calculations and store predictions

    div_h2h_team2 = home_away_soup.find("div", {"id": "h2h-team2"})

    # Find the table within the div
    tabley = div_h2h_team2.find("table", {"id": "btable"})

    # Extract header and rows
    header = [th.text.strip() for th in tabley.find_all("th")]

    rows = [row.find_all('td') for row in tabley.find_all("tr")[1:]]
    team_data_away = {'header': header, 'rows': [
        [col.text.strip() for col in row] for row in rows[1:]]}
    # print(team_data)

    home_row = None
    for row in team_data['rows']:
        if row[1] == first_item:
            home_row = row
            break

    # Print the second row of text for 'Coventry City' if found
    if home_row:
        homewin = home_row[3]
        homedraw = home_row[4]
        homeloss = home_row[5]

        print(homewin)
        print(homedraw)
        print(homeloss)

    away_row = None
    for row in team_data_away['rows']:
        if row[1] == second_item:
            away_row = row
            break

    if away_row:
        awaywin = away_row[3]
        awaydraw = away_row[4]
        awayloss = away_row[5]
        # print(homeloss)
        print(awaywin)
        print(awaydraw)
        print(awayloss)

    total_games = int(awaydraw)+int(awaywin)+int(awayloss) + \
        int(homewin)+int(homedraw)+int(homeloss)
    home_win_prob = ("{: 0.2f}".format(
        ((int(homewin)+int(awayloss))*100)/int(total_games)))
    draw_prob = ("{: 0.2f}".format(
        ((int(homedraw)+int(awaydraw))*100)/int(total_games)))
    away_win_prob = ("{: 0.2f}".format(
        ((int(homeloss)+int(awaywin))*100)/int(total_games)))

    probs = f'{home_win_prob} , {draw_prob} , {away_win_prob}'
    print(probs)
    return {
        'home_win_prob': home_win_prob,
        'draw_prob': draw_prob,
        'away_win_prob': away_win_prob
    }


class GeneralPrediction(APIView):
    def get(self, request):
        current_datetime = date.today()

        # cache_key = f'general_prediction_{current_datetime}'

        # # Check if the response is already cached
        # cached_response = cache.get(cache_key)
        # if cached_response:
        #     return Response(cached_response, status=status.HTTP_200_OK)

        if LP.objects.filter(date=current_datetime).exists():
            response = LP.objects.get(date=current_datetime).content

            # cache.set(cache_key, response, timeout=24*60*60)  # Cache for 24 hours
            return Response(response, status=status.HTTP_200_OK)

        else:
            base_url = 'https://www.soccerstats.com/'
            matchday_url = f'{base_url}matches.asp?matchday=1&listing=1'

            try:
                # Fetch data for matchday
                matchday_soup = fetch_data(matchday_url)
                if not matchday_soup:
                    return redirect('outcome')

                table = matchday_soup.find('table', {'id': 'btable'})
                rows = table.find('tbody').find_all('tr')
                countries_to_check = [
                    'spain', 'england', 'italy', 'france', 'germany', 'germany2', 'norway', 'norway2', 'iceland', 'sweden', 'sweden2', 'portugal', 'netherlands', 'netherlands2',
                    'russia', 'belgium', 'turkey', 'ukraine', 'faroeislands', 'czechrepublic', 'austria', 'switzerland', 'greece', 'scotland', 'croatia',
                    'denmark', 'poland', 'spain2', 'england2', 'italy2', 'france2', 'armenia',
                    'belarus', 'brazil', 'china', 'japan', 'southkorea', 'estonia',
                    'georgia', 'ireland', 'kazakhstan', 'latvia', 'lithuania', 'moldova', 'wales', 'vietnam', 'kazakhstan', 'finland'
                ]
                unique_alt_texts = {row.find('td').get(
                    'sorttable_customkey', '') for row in rows if row.get('height') == '36'}
                available_countries = [
                    country for country in countries_to_check if country in unique_alt_texts]

                all_response_data = []

                for league in available_countries:
                    # Fetch data for league table
                    avgtable_url = f'{base_url}table.asp?league={league}&tid=d'
                    avgtable_soup = fetch_data(avgtable_url)
                    if not avgtable_soup:
                        continue

                    table = avgtable_soup.find("table", {"id": 'btable'})
                    header = [h.text.strip() for h in table.find_all("th")]
                    rows = [row.find_all('td')
                            for row in table.find_all("tr")[1:]]
                    league_data = {'header': header, 'rows': [
                        [col.text.strip() for col in row] for row in rows[1:]]}
                    # print(league_data)

                    # Fetch data for fixture list and predictions
                    fixture_url = f'{base_url}latest.asp?league={league}'
                    fixture_soup = fetch_data(fixture_url)
                    if not fixture_soup:
                        continue

                    odd_rows = fixture_soup.find_all('tr', {'height': '32'})
                    cols = [col.text.strip() for row in odd_rows for col in row.find_all('td', {'style': [
                        'text-align:right;padding-right:8px;', 'text-align:left;padding-left:8px;']})]

                    # Extract teams and other information
                    teams = [row[0] for row in league_data['rows']]
                    # print(teams)
                    home_avg = away_avg = 100.000
                    table = fixture_soup.find(
                        "table", style="margin-left:14px;margin-riht:14px;border:1px solid #aaaaaa;border-radius:12px;overflow:hidden;")
                    if table:
                        b_tags = table.find_all("b")
                        if len(b_tags) >= 9:
                            home_avg = float(b_tags[8].text)
                        if len(b_tags) >= 11:
                            away_avg = float(b_tags[10].text)

                    # Perform calculations and store predictions
                    for i in range(0, len(cols), 2):
                        first_item, second_item = cols[i], cols[i + 1]
                        if first_item in teams and second_item in teams:

                            home_index, away_index = teams.index(
                                first_item), teams.index(second_item)
                            row_list, row_list_away = league_data['rows'][
                                home_index], league_data['rows'][away_index]

                            H1, H2 = float(
                                row_list[6]) / home_avg, float(row_list_away[11]) / home_avg
                            home_goal = float(H1) * float(H2) * home_avg
                            A1, A2 = float(
                                row_list[7]) / away_avg, float(row_list_away[10]) / away_avg
                            away_goal = float(A1) * float(A2) * away_avg
                            threematch_goals_probability = "{:0.2f}".format(
                                (1 - poisson.cdf(k=3, mu=home_goal + away_goal)) * 100)
                            twomatch_goals_probability = "{:0.2f}".format(
                                (1 - poisson.cdf(k=2, mu=home_goal + away_goal)) * 100)

                            most_likely_outcome, most_likely_prob_percent = calculate_poisson_probs(
                                home_goal, away_goal)

                            # Predict the likelihood of home team winning, away team winning, or draw
                            result, result_prob = predict_match_result(
                                home_goal, away_goal)

                            # Get top 3 probable scorelines
                            probable_scorelines = get_top_probable_scorelines(
                                home_goal, away_goal, n=5)

                            # win_prob = win_probability(league, first_item, second_item)
                            # print(win_prob.home_win_prob)

                            response_data = {
                                'prediction': f"{first_item} {most_likely_outcome[0]} vs {second_item} {most_likely_outcome[1]}",
                                'over_2.5_prob': f"{threematch_goals_probability}%",
                                'over_1.5_prob': f"{twomatch_goals_probability}%",
                                'league': f"{league}",
                                # 'match_result': result,
                                # 'match_result_prob': result_prob,
                                'top_scorelines': f"{probable_scorelines}",
                                # 'home_win_prob': home_win_prob,
                                # 'draw_prob': draw_prob,
                                # 'away_win_prob': away_win_prob,
                            }
                            all_response_data.append(response_data)
                            print(all_response_data)

                # Store predictions in the database
                predictionx = LP.objects.create(content=all_response_data)
                predictionx.save()
                # cache.set(cache_key, all_response_data, timeout=24*60*60)

                return Response(all_response_data, status=status.HTTP_200_OK)

            except Exception as e:
                return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LeaguePrediction(APIView):

    def post(self, request):
        league = request.data.get('league')
        if not league:
            return Response({'error': 'League parameter is required.'}, status=status.HTTP_400_BAD_REQUEST)

        base_url = 'https://www.soccerstats.com/'
        urlavgtable = f'https://www.soccerstats.com/table.asp?league={league}&tid=d'
        urlfixture = f'https://www.soccerstats.com/latest.asp?league={league}'

        try:
            # Fetch league table data
            response = requests.get(urlavgtable)
            soup = BeautifulSoup(response.content, "html.parser")
            table = soup.find("table", {"id": "btable"})
            header = table.find_all("th")
            header = [h.text.strip() for h in header]
            rows = table.find_all("tr")[1:]
            league_data[league] = {'header': header, 'rows': []}

            for row in rows[1:]:
                cols = row.find_all('td')
                cols = [col.text.strip() for col in cols]
                league_data[league]['rows'].append(cols)
                print(league_data[league])

            # Send the fixture list and the predictions
            res = requests.get(urlfixture)
            soup = BeautifulSoup(res.content, 'html.parser')
            odd_rows = soup.find_all('tr', {'height': '32'})
            cols = []
            for row in odd_rows:
                cols.extend(row.find_all('td', {'style': [
                            'text-align:right;padding-right:8px;', 'text-align:left;padding-left:8px;']}))

            output = [col.text.strip() for col in cols]

            teams = [row[0] for row in league_data[league]['rows']]

            b_tags = soup.find_all('b')
            table = soup.find(
                "table", style="margin-left:14px;margin-riht:14px;border:1px solid #aaaaaa;border-radius:12px;overflow:hidden;")

            Home_avg = float(100.000)
            if table:
                b_tags = table.find_all("b")
                if len(b_tags) >= 9:
                    Home_avg = b_tags[8].text

            Away_avg = float(100.000)
            if table:
                b_tags = table.find_all("b")
                if len(b_tags) >= 11:
                    Away_avg = b_tags[10].text

            H3a = Home_avg
            A3a = Away_avg
            H3 = float(H3a)
            A3 = float(A3a)
            predictions_list = []

            for i in range(0, len(output), 2):
                first_item = output[i]
                second_item = output[i+1]
                if first_item in teams:
                    row_list = league_data[league]['rows'][teams.index(
                        first_item)]
                    print(first_item)
                if second_item in teams:
                    row_listaway = league_data[league]['rows'][teams.index(
                        second_item)]
                    print(second_item)

                H1 = ("{:0.2f}".format(float(row_list[6])/H3))
                print(row_list[6])
                H2 = ("{:0.2f}".format(float(row_listaway[11])/H3))
                print(row_listaway[11])
                Home_goal = ("{:0.2f}".format(
                    float(H1) * float(H2) * float(H3)))
                A1 = ("{:0.2f}".format(float(row_list[7])/A3))
                print(row_list[7])
                A2 = ("{:0.2f}".format(float(row_listaway[10])/A3))
                print(row_listaway[10])
                Away_goal = ("{:0.2f}".format(
                    float(A1) * float(A2) * float(A3)))
                twomatch_goals_probability = ("{:0.2f}".format(
                    (1-poisson.cdf(k=2, mu=float(float(Home_goal) + float(Away_goal))))*100))
                threematch_goals_probability = ("{:0.2f}".format(
                    (1-poisson.cdf(k=3, mu=float(float(Home_goal) + float(Away_goal))))*100))

                lambda_home = float(Home_goal)
                lambda_away = float(Away_goal)

                score_probs = [[poisson.pmf(i, team_avg) for i in range(
                    0, 10)] for team_avg in [lambda_home, lambda_away]]

                outcomes = [[i, j]
                            for i in range(0, 10) for j in range(0, 10)]

                probs = [score_probs[0][i] * score_probs[1][j]
                         for i, j in outcomes]

                most_likely_outcome = outcomes[probs.index(max(probs))]

                most_likely_prob_percent = max(probs) * 100

                prediction_data = {
                    'prediction': f"{first_item} {most_likely_outcome[0]} vs {second_item} {most_likely_outcome[1]}",
                    'over_2.5_prob': f"{threematch_goals_probability}%",
                    'over_1.5_prob': f"{twomatch_goals_probability}%"
                }
                predictions_list.append(prediction_data)

            return Response(predictions_list, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
